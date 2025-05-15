# tasks.py
import io, os, uuid, zipfile
from celery import shared_task, group, chord
from django.conf import settings

from app.utils import (
    parse_file_content,
    reconstruct_file_content,
    chunk_dict,
    translate_text,
)

SEPARATOR  = "|||"
CHUNK_SIZE = 30


@shared_task
def translate_language_task(parsed_content, base_name, ext, language, context, description):
    """
    1) Splits parsed_content into chunks,
    2) Calls translate_text for each chunk (internally parallel if you like),
    3) Reassembles full dict → file‐string,
    4) Returns (language, bytes_of_file, total_tokens)
    """
    # --- your existing translate_language logic, but output a bytes blob ---
    translated_dict, total_tokens = {}, 0
    for chunk_index, chunk in enumerate(chunk_dict(parsed_content, CHUNK_SIZE)):
        pairs = [f"{k} => {v}" for k, v in chunk.items()]
        combined = SEPARATOR.join(pairs)
        prompt = f"""
                    You will receive a list of key-value pairs separated by "{SEPARATOR}".
                    Translate only the **values** into {language}, keeping the keys unchanged.
                    Ensure each output pair follows the format: key => translated_value.
                    Do not skip any values. Preserve the order.
                    Do NOT translate the delimiter (`|||`).
                    Do NOT translate the new line (`\n`).
                    Only translate the human-readable parts.
                    Output MUST use the exact same `|||` separator between translated segments.
                    Do NOT wrap the result in quotation marks or code blocks.
                        """
        resp = translate_text(
            combined,
            language,
            "PLAIN_TEXT",
            context,
            description,
            prompt=prompt,
            chunk_index=chunk_index
        )
        total_tokens += resp.get("total_token", 0)
        for raw in resp["content"].split(SEPARATOR):
            k, v = raw.split("=>", 1)
            translated_dict[k.strip()] = v.strip()

    file_str = reconstruct_file_content(translated_dict, ext.lstrip("."))  # e.g. "json", "csv"
    return {
        "language": language,
        "content": file_str.encode("utf-8"),
        "tokens": total_tokens,
        "filename": f"{base_name}_{language}{ext}",
    }


@shared_task
def zip_results_task(results, base_name):
    """
    1) Accepts list of dicts from translate_language_task,
    2) Builds one in-memory ZIP,
    3) Saves to MEDIA_ROOT and returns URL + total tokens.
    """
    zip_buf = io.BytesIO()
    total_tokens = 0

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for res in results:
            total_tokens += res["tokens"]
            zf.writestr(res["filename"], res["content"])

    unique_id  = uuid.uuid4().hex[:8]
    zip_name   = f"{base_name}_{unique_id}_translated.zip"
    zip_path   = os.path.join(settings.MEDIA_ROOT, zip_name)
    with open(zip_path, "wb") as f:
        f.write(zip_buf.getvalue())

    return {
        "zip_path":    zip_path,
        "download_url": f"{settings.MEDIA_URL}{zip_name}",
        "total_tokens": total_tokens,
    }


@shared_task(bind=True)
def translate_and_package(self, file_name, file_content, target_languages,
                          file_format, context, description):
    """
    Orchestrator task: parse once, then fire a group of per-language subtasks,
    followed by a chord callback that zips them all up.
    """
    base_name, ext = os.path.splitext(file_name)
    parsed = parse_file_content(file_content, file_format)

    # Build one sub‐task per language
    lang_group = group(
        translate_language_task.s(parsed, base_name, ext, lang, context, description)
        for lang in target_languages
    )

    # Chord: when all lang tasks finish, run zip_results_task
    workflow = chord(
        lang_group,
        zip_results_task.s(base_name)
    )

    # .apply_async gives us an AsyncResult we can track
    result = workflow.apply_async()

    # If you want to return the chord’s task id so the caller can poll:
    return {"task_id": result.id}
