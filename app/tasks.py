import uuid
import io
import os
import zipfile
from celery import shared_task
from django.conf import settings
from concurrent.futures import ThreadPoolExecutor, as_completed

from celery import shared_task
import io, os, uuid, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings

from app.utils import parse_content, build_content, chunk_dict,parse_file_content,reconstruct_file_content


SEPARATOR = "|||"  # Unique separator unlikely to appear in content

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
        # for language in target_languages:
        #     futures.append(
        #         executor.submit(
        #             translate_language,
        #             parsed_content,
        #             language,
        #             file_format,
        #             context,
        #             description
        #         )
        #     )

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
    from .views import translate_text
    from concurrent.futures import ThreadPoolExecutor, as_completed

    translated_result = {}
    total_tokens = 0

    chunks = list(chunk_dict(parsed_content, 10))

    def translate_chunk(chunk,index=None):
        pairs = [f"{key} => {value}" for key, value in chunk.items()]
        combined_text = SEPARATOR.join(pairs)

        prompt = f"""
            You will receive a list of key-value pairs separated by "{SEPARATOR}".
            Translate only the **values** into {target_language}, keeping the keys unchanged.
            Ensure each output pair follows the format: key => translated_value.
            Do not skip any values. Preserve the order.
            Do NOT translate the delimiter (`|||`).
            Do NOT translate the new line (`\n`).
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

    # def translate_chunk(chunk):
    #     keys = list(chunk.keys())
    #     values = list(chunk.values())
    #     combined_text = SEPARATOR.join(values)
    #
    #     translated_combined = translate_text(
    #         combined_text,
    #         target_language,
    #         file_format,
    #         context,
    #         description
    #     )
    #
    #     translated_values = translated_combined["content"].split(SEPARATOR)
    #     translated_chunk = dict(zip(keys, translated_values))
    #     return translated_chunk, translated_combined.get("total_token", 0)

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(translate_chunk, chunk,index) for index, chunk in enumerate(chunks)]

        for future in as_completed(futures):
            translated_chunk, chunk_tokens = future.result()
            translated_result.update(translated_chunk)
            total_tokens += chunk_tokens

    return translated_result, total_tokens


# def translate_language(parsed_content, target_language, file_format, context, description):
#     from .views import translate_text
#
#     translated_result = {}
#     total_tokens = 0
#
#     for chunk in chunk_dict(parsed_content, 50):
#         keys = list(chunk.keys())
#         values = list(chunk.values())
#
#         combined_text = SEPARATOR.join(values)
#
#         translated_combined = translate_text(
#             combined_text,
#             target_language,
#             file_format,
#             context,
#             description
#         )
#
#         translated_values = translated_combined["content"].split(SEPARATOR)
#
#         # Map translated values back to keys
#         translated_chunk = dict(zip(keys, translated_values))
#         translated_result.update(translated_chunk)
#         total_tokens += translated_combined.get("total_token", 0)
#
#     return translated_result, total_tokens


# def translate_language(parsed_content, language, file_format, context, description):
#     translated_content = {}
#     total_token = 0
#
#     with ThreadPoolExecutor() as key_executor:
#         key_futures = {key_executor.submit(translate_value, value, language, context, description): key for key, value in parsed_content.items()}
#
#         for future in as_completed(key_futures):
#             key = key_futures[future]
#             translated_value = future.result()
#             translated_content[key] = translated_value
#             # If you want token count per key, modify translate_value to return token info
#
#     final_text = build_content(translated_content, file_format)
#     return final_text, total_token


# @shared_task(bind=True)
# def translate_and_package(self, file_name, content, target_languages, file_format, context, description):
#     from .views import translate_text  # dynamic import
#
#     results = {}
#     zip_buffer = io.BytesIO()
#     total_token = 0
#
#     base_name = os.path.splitext(file_name)[0]
#     progress_steps = len(target_languages)
#     completed_steps = 0
#
#     parsed_content = parse_content(content, file_format)
#
#     with ThreadPoolExecutor() as lang_executor:
#         language_futures = {}
#
#         for language in target_languages:
#             language_futures[language] = lang_executor.submit(
#                 translate_language,
#                 parsed_content,
#                 language,
#                 file_format,
#                 context,
#                 description
#             )
#
#         for i, future in enumerate(as_completed(language_futures.values())):
#             language = list(language_futures.keys())[i]
#             translated_text, language_token = future.result()
#             translated_filename = f"{base_name}_{language}{os.path.splitext(file_name)[1]}"
#             translated_path = os.path.join(settings.MEDIA_ROOT, translated_filename)
#
#             with open(translated_path, "w", encoding="utf-8") as f:
#                 f.write(translated_text)
#
#             results[language] = translated_path
#             total_token += language_token
#
#             completed_steps += 1
#             progress_percent = int((completed_steps / progress_steps) * 90)
#             self.update_state(state='PROGRESS', meta={'progress': progress_percent})
#
#     # Create zip file
#     unique_id = uuid.uuid4().hex[:8]
#     zip_filename = f"{base_name}_{unique_id}_translated.zip"
#     zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)
#
#     with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
#         for path in results.values():
#             zip_file.write(path, os.path.basename(path))
#
#     with open(zip_path, "wb") as f:
#         f.write(zip_buffer.getvalue())
#
#     self.update_state(state='PROGRESS', meta={'progress': 100})
#
#     return {
#         "status": "completed",
#         "zip_path": zip_path,
#         "download_url": f"{settings.MEDIA_URL}{zip_filename}",
#         "total_token": total_token,
#         "progress": 100
#     }
#

# @shared_task(bind=True)
# def translate_and_package(self, file_name, content, target_languages, file_format, context, description):
#     from .views import translate_text  # avoid circular import
#
#     results = {}
#     zip_buffer = io.BytesIO()
#     total_token = 0
#
#     base_name = os.path.splitext(file_name)[0]
#     futures = []
#     progress_steps = len(target_languages)
#     completed_steps = 0
#
#     with ThreadPoolExecutor() as executor:
#         for language in target_languages:
#             futures.append(
#                 executor.submit(
#                     translate_text,
#                     content,
#                     language,
#                     file_format,
#                     context,
#                     description
#                 )
#             )
#
#         for i, future in enumerate(as_completed(futures)):
#             language = target_languages[i]
#             translated_content = future.result()
#             translated_filename = f"{base_name}_{language}{os.path.splitext(file_name)[1]}"
#             translated_path = os.path.join(settings.MEDIA_ROOT, translated_filename)
#
#             with open(translated_path, "w", encoding="utf-8") as f:
#                 f.write(translated_content.get("content"))
#
#             results[language] = translated_path
#             total_token += translated_content.get("total_token")
#
#             # Update progress
#             completed_steps += 1
#             progress_percent = int((completed_steps / progress_steps) * 90)  # Keep 10% for zipping
#             self.update_state(state='PROGRESS', meta={'progress': progress_percent})
#
#     # Generate a unique zip file name using uuid
#     unique_id = uuid.uuid4().hex[:8]
#     zip_filename = f"{base_name}_{unique_id}_translated.zip"
#     zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)
#
#     with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
#         for path in results.values():
#             zip_file.write(path, os.path.basename(path))
#
#     with open(zip_path, "wb") as f:
#         f.write(zip_buffer.getvalue())
#
#     # Final progress update
#     self.update_state(state='PROGRESS', meta={'progress': 100})
#
#     return {
#         "status": "completed",
#         "zip_path": zip_path,
#         "download_url": f"{settings.MEDIA_URL}{zip_filename}",
#         "total_token": total_token,
#         "progress": 100
#     }


# @shared_task
# def translate_and_package(file_name, content, target_languages, file_format, context, description):
#     from .views import translate_text  # import here to avoid circular import
#
#     results = {}
#     zip_buffer = io.BytesIO()
#     total_token = 0
#
#     # Make a base name for all translated files
#     base_name = os.path.splitext(file_name)[0]
#     futures = []
#     with ThreadPoolExecutor() as executor:
#         for language in target_languages:
#             futures.append(
#                 executor.submit(
#                     translate_text,
#                     content,
#                     language,
#                     file_format,
#                     context,
#                     description
#                 )
#             )
#
#         total_token = 0
#         for i, future in enumerate(as_completed(futures)):
#             language = target_languages[i]
#             translated_content = future.result()
#             translated_filename = f"{base_name}_{language}{os.path.splitext(file_name)[1]}"
#             translated_path = os.path.join(settings.MEDIA_ROOT, translated_filename)
#
#             with open(translated_path, "w", encoding="utf-8") as f:
#                 f.write(translated_content.get("content"))
#
#             results[language] = translated_path
#             total_token += translated_content.get("total_token")
#
#         # if usage.exists():
#         #     usage = usage.first()
#         #     usage.total_token = total_token
#         #     usage.save()
#
#     # for language in target_languages:
#     #     translated_content = translate_text(content, language, file_format, context, description)
#     #     # print(translated_content)
#     #     translated_filename = f"{base_name}_{language}{os.path.splitext(file_name)[1]}"
#     #     translated_path = os.path.join(settings.MEDIA_ROOT, translated_filename)
#     #
#     #     with open(translated_path, "w", encoding="utf-8") as f:
#     #         f.write(translated_content["content"])
#     #
#     #     results[language] = translated_path
#     #     total_token += translated_content["total_token"]
#
#     # Generate a unique zip file name using uuid
#     unique_id = uuid.uuid4().hex[:8]
#     zip_filename = f"{base_name}_{unique_id}_translated.zip"
#     zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)
#
#     with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
#         for language, path in results.items():
#             zip_file.write(path, os.path.basename(path))
#
#     with open(zip_path, "wb") as f:
#         f.write(zip_buffer.getvalue())
#
#     return {
#         "zip_path": zip_path,
#         "download_url": f"{settings.MEDIA_URL}{zip_filename}",
#         "total_token": total_token
#     }
