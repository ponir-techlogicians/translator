from celery import shared_task
import io, os, uuid, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings

from app.utils import parse_content, build_content, chunk_dict, parse_file_content, reconstruct_file_content, \
    translate_text

SEPARATOR = "|||"  # Unique separator unlikely to appear in content
CHUNK_SIZE = 10

@shared_task(bind=True)
def translate_and_package(self, file_name, content, target_languages, file_format, context, description):
    from .views import translate_text   # assumed helper functions

    results = {}
    zip_buffer = io.BytesIO()
    total_token = 0

    base_name = os.path.splitext(file_name)[0]
    futures = []
    progress_steps = len(target_languages)
    completed_steps = 0

    # Step 1: Parse input file into a dictionary (key-value)
    parsed_content = parse_file_content(content, file_format)

    with ThreadPoolExecutor() as executor:

        future_to_language = {
            executor.submit(
                translate_language,
                parsed_content,
                language,
                file_format,
                context,
                description
            ): language
            for language in target_languages
        }

        for future in as_completed(future_to_language):
            language = future_to_language[future]
            translated_content, language_total_token = future.result()
            translated_filename = f"{base_name}_{language}{os.path.splitext(file_name)[1]}"
            translated_path = os.path.join(settings.MEDIA_ROOT, translated_filename)

            # Step 7: Rebuild translated file
            file_content = reconstruct_file_content(translated_content, file_format)
            with open(translated_path, "w", encoding="utf-8") as f:
                f.write(file_content)

            results[language] = translated_path
            total_token += language_total_token

            # Update progress
            completed_steps += 1
            progress_percent = int((completed_steps / progress_steps) * 90)
            self.update_state(state='PROGRESS', meta={'progress': progress_percent})

    # Step 8: Zip the translated files
    unique_id = uuid.uuid4().hex[:8]
    zip_filename = f"{base_name}_{unique_id}_translated.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in results.values():
            zip_file.write(path, os.path.basename(path))

    with open(zip_path, "wb") as f:
        f.write(zip_buffer.getvalue())

    self.update_state(state='PROGRESS', meta={'progress': 100})

    return {
        "status": "completed",
        "zip_path": zip_path,
        "download_url": f"{settings.MEDIA_URL}{zip_filename}",
        "total_token": total_token,
        "progress": 100
    }

def translate_value(value, language, context, description):
    # avoid circular import
    from .views import translate_text
    return translate_text(value, language, "plain_text", context, description)["content"]


def translate_language(parsed_content, target_language, file_format, context, description):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    translated_result = {}
    total_tokens = 0

    chunks = list(chunk_dict(parsed_content, CHUNK_SIZE))

    def translate_chunk(chunk,index=None):
        pairs = [f"{key} => {value}" for key, value in chunk.items()]
        combined_text = SEPARATOR.join(pairs)

        prompt = f"""
            You will receive a list of key-value pairs separated by "{SEPARATOR}".
            Translate only the **values** into {target_language}, keeping the keys unchanged.
            The original language is in korean.
            Ensure each output pair follows the format: key => translated_value.
            Do not skip any values. Preserve the order.
            Do NOT translate the delimiter (`|||`).
            You must preserve every line break exactly.
            Only translate the human-readable parts.
            Output MUST use the exact same `|||` separator between translated segments.
            Do NOT wrap the result in quotation marks or code blocks.
                """

        translated_combined = translate_text(
            combined_text,
            target_language,
            file_format,
            context,
            description,
            prompt=prompt,# Pass this custom prompt to your `translate_text` function,
            chunk_index = index
        )

        translated_pairs = translated_combined["content"].split(SEPARATOR)

        translated_chunk = {}
        for pair in translated_pairs:
            #print(pair)
            if "=>" in pair:
                key, value = pair.split("=>", 1)
                translated_chunk[key.strip()] = value.strip()
            else:
                print(f"[Warning] Malformed pair in language {target_language}: '{pair}'")


        return translated_chunk, translated_combined.get("total_token", 0)

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(translate_chunk, chunk,index) for index, chunk in enumerate(chunks)]

        for future in as_completed(futures):
            translated_chunk, chunk_tokens = future.result()
            translated_result.update(translated_chunk)
            total_tokens += chunk_tokens

    return translated_result, total_tokens