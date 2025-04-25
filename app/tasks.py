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

@shared_task(bind=True)
def translate_and_package(self, file_name, content, target_languages, file_format, context, description):
    from .views import translate_text  # avoid circular import

    results = {}
    zip_buffer = io.BytesIO()
    total_token = 0

    base_name = os.path.splitext(file_name)[0]
    futures = []
    progress_steps = len(target_languages)
    completed_steps = 0

    with ThreadPoolExecutor() as executor:
        for language in target_languages:
            futures.append(
                executor.submit(
                    translate_text,
                    content,
                    language,
                    file_format,
                    context,
                    description
                )
            )

        for i, future in enumerate(as_completed(futures)):
            language = target_languages[i]
            translated_content = future.result()
            translated_filename = f"{base_name}_{language}{os.path.splitext(file_name)[1]}"
            translated_path = os.path.join(settings.MEDIA_ROOT, translated_filename)

            with open(translated_path, "w", encoding="utf-8") as f:
                f.write(translated_content.get("content"))

            results[language] = translated_path
            total_token += translated_content.get("total_token")

            # Update progress
            completed_steps += 1
            progress_percent = int((completed_steps / progress_steps) * 90)  # Keep 10% for zipping
            self.update_state(state='PROGRESS', meta={'progress': progress_percent})

    # Generate a unique zip file name using uuid
    unique_id = uuid.uuid4().hex[:8]
    zip_filename = f"{base_name}_{unique_id}_translated.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in results.values():
            zip_file.write(path, os.path.basename(path))

    with open(zip_path, "wb") as f:
        f.write(zip_buffer.getvalue())

    # Final progress update
    self.update_state(state='PROGRESS', meta={'progress': 100})

    return {
        "status": "completed",
        "zip_path": zip_path,
        "download_url": f"{settings.MEDIA_URL}{zip_filename}",
        "total_token": total_token,
        "progress": 100
    }


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
