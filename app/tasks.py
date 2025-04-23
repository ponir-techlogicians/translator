import uuid
import io
import os
import zipfile
from celery import shared_task
from django.conf import settings

@shared_task
def translate_and_package(file_name, content, target_languages, file_format, context, description):
    from .views import translate_text  # import here to avoid circular import

    results = {}
    zip_buffer = io.BytesIO()
    total_token = 0

    # Make a base name for all translated files
    base_name = os.path.splitext(file_name)[0]

    for language in target_languages:
        translated_content = translate_text(content, language, file_format, context, description)
        translated_filename = f"{base_name}_{language}{os.path.splitext(file_name)[1]}"
        translated_path = os.path.join(settings.MEDIA_ROOT, translated_filename)

        with open(translated_path, "w", encoding="utf-8") as f:
            f.write(translated_content["content"])

        results[language] = translated_path
        total_token += translated_content["total_token"]

    # Generate a unique zip file name using uuid
    unique_id = uuid.uuid4().hex[:8]
    zip_filename = f"{base_name}_{unique_id}_translated.zip"
    zip_path = os.path.join(settings.MEDIA_ROOT, zip_filename)

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for language, path in results.items():
            zip_file.write(path, os.path.basename(path))

    with open(zip_path, "wb") as f:
        f.write(zip_buffer.getvalue())

    return {
        "zip_path": zip_path,
        "download_url": f"{settings.MEDIA_URL}{zip_filename}",
        "total_token": total_token
    }
