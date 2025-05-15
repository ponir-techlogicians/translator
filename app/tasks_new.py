# tasks.py

import uuid
import io
import zipfile
from celery import shared_task, chord
from django.conf import settings
from app.utils import parse_file_content, reconstruct_file_content
from app.utils import translate_text
import tiktoken

def chunk_by_token_limit(kv_dict, max_tokens, separator="|||"):
    """
    Yield sub-dicts of kv_dict where the total token count (by GPT-4 encoding)
    of "key=>value" pairs plus separators does not exceed max_tokens.
    """
    enc = tiktoken.encoding_for_model("gpt-4")
    items = list(kv_dict.items())
    cur = {}
    count = 0
    for k, v in items:
        text = f"{k}=>{v}"
        tok = len(enc.encode(text + separator))
        if cur and count + tok > max_tokens:
            yield cur
            cur = {}
            count = 0
        cur[k] = v
        count += tok
    if cur:
        yield cur

@shared_task(bind=True)
def translate_language_task(self, parsed_content, language, context, description, chunk_size_tokens=3500):
    """
    Translate parsed_content dict into target 'language' using OpenAI API.
    """
    translated = {}
    total_tokens = 0

    for chunk in chunk_by_token_limit(parsed_content, chunk_size_tokens):
        combined = "|||".join(f"{k}=>{v}" for k, v in chunk.items())
        resp = translate_text(
            combined,
            language,
            file_format="plain_text",
            context=context,
            description=description,
            prompt=(
                f"You will receive key=>value pairs separated by '|||'.\n"
                f"Translate only the values into {language}, keep keys unchanged.\n"
                "Do not translate separators or quotation marks."
            )
        )
        total_tokens += resp.get("total_tokens", 0)
        for pair in resp["content"].split("|||"):
            if "=>" in pair:
                k, v = pair.split("=>", 1)
                translated[k.strip()] = v.strip()

    return {'language': language, 'translated': translated, 'tokens': total_tokens}

@shared_task(bind=True)
def package_translations_task(self, results, file_name, file_format):
    """
    Zip up all translated language results into a single .zip file.
    """
    base, ext = file_name.rsplit(".", 1)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for res in results:
            text = reconstruct_file_content(res['translated'], file_format)
            fname = f"{base}_{res['language']}.{file_format}"
            zf.writestr(fname, text)

    unique = uuid.uuid4().hex[:8]
    zip_name = f"{base}_{unique}_translated.zip"
    zip_path = settings.MEDIA_ROOT / zip_name
    zip_path.write_bytes(zip_buffer.getvalue())

    return {
        'zip_path': str(zip_path),
        'download_url': f"{settings.MEDIA_URL}{zip_name}",
        'total_tokens': sum(r['tokens'] for r in results)
    }

@shared_task(bind=True)
def translate_and_package(self, file_name, content, target_languages, file_format, context, description):
    """
    Entry point: parse file, dispatch translation tasks in parallel via a Celery chord,
    then package and return the AsyncResult for downstream tracking.
    """
    parsed = parse_file_content(content, file_format)
    header = [
        translate_language_task.s(parsed, lang, context, description)
        for lang in target_languages
    ]
    callback = package_translations_task.s(file_name, file_format)
    job = chord(header, callback)()
    return job  # AsyncResult; you can use job.id or job.get() in your view
