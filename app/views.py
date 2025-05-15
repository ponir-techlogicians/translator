import openai
import os
import polib
import io
import zipfile
import tiktoken
from django.conf import settings
from django.shortcuts import render
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import get_valid_filename
from concurrent.futures import ThreadPoolExecutor, as_completed
import stripe
from app.tasks import translate_and_package
from app.models import Usage
from celery.result import AsyncResult
stripe.api_key = settings.STRIPE_SECRET_KEY
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)


def count_tokens(text, model="gpt-4-turbo"):
    """Estimate the token count of a given text for a specific model."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

def count_bytes(text):
    return len(text.encode('utf-8'))

def translate_text(text, target_language, file_format=None, context=None, description=None,prompt=None,chunk_index=None):
    """
    Translate a separator-joined batch of plain values using OpenAI API.
    Preserves order and assumes each segment is a user-facing string.
    """
    if not prompt:
        format_instruction = f"The content is in `{file_format}` format." if file_format else ""
        context_instruction = f"Context: {context.strip()}" if context else ""
        description_instruction = f"Description: {description.strip()}" if description else ""

        prompt = f"""
        You are a professional translation assistant.
        
        Each line or segment in the user message is a separate string to be translated. The segments are separated by the delimiter: `|||`.
        
        {format_instruction}
        {context_instruction}
        {description_instruction}
        
        Translate each segment into **{target_language}**, preserving their order.
        Do NOT combine, remove, or reorder segments.
        Do NOT translate the delimiter (`|||`).
        Do not skip any segment. Even short or placeholder text must be translated.
        Only translate the human-readable parts.
        
        Output MUST use the exact same `|||` separator between translated segments.
        Do NOT wrap the result in quotation marks or code blocks.
        
        Translate each segment separated by `|||` into {target_language}.
        Ensure the output has the exact same number of segments, separated by `|||`.
        """

    # print(prompt)

    print(f"Translating to {target_language} {chunk_index}...")

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        temperature=0.2,
        messages=[
            {"role": "system", "content": prompt.strip()},
            {"role": "user", "content": text}
        ]
    )

    print(f"Translation complete: {target_language} {chunk_index}")

    return {
        "content": response.choices[0].message.content.strip(),
        "total_token": response.usage.total_tokens
    }


# def translate_text(text, target_language, file_format=None, context=None, description=None):
#     """Translate entire file content using OpenAI API with context and description"""
#
#     format_instruction = f"The following is a {file_format} file." if file_format else ""
#     context_instruction = f"Context: {context}." if context else ""
#     description_instruction = f"Description: {description}." if description else ""
#
#     prompt = f"""
#     {format_instruction}
#     {context_instruction}
#     {description_instruction}
#     Translate the entire content into {target_language}. Keep the structure unchanged.
#     """
#
#     # prompt_tokens = count_tokens(prompt)
#     # text_tokens = count_tokens(text)
#     # estimated_total_tokens = prompt_tokens + text_tokens
#     #
#     # print(f"Estimated token usage: {estimated_total_tokens} tokens")
#
#     # prompt_bytes = count_tokens(prompt)
#     # print(prompt_bytes)
#     # text_bytes = count_tokens(text)
#     # estimated_total_bytes = prompt_bytes + text_bytes
#     # print(f"Estimated total bytes: {estimated_total_bytes}")
#
#     print('Translating to '+target_language+'....')
#
#     response = client.chat.completions.create(
#         model="gpt-4-turbo",
#         messages=[
#             {"role": "system", "content": prompt.strip()},
#             {"role": "user", "content": text}
#         ]
#     )
#     print(response)
#     print('Translating complete '+target_language+'.')
#
#
#     return { "content": response.choices[0].message.content, "total_token": response.usage.total_tokens }


def get_file_format(file_name):
    """Determine the format of the uploaded file based on its extension"""
    extension_mapping = {
        ".json": "JSON",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".po": "PO",
        ".php": "PHP",
        ".ini": "INI",
        ".xml": "XML",
        ".csv": "CSV",
        ".ts": "TS",
        ".xliff": "XLIFF",
    }
    return extension_mapping.get(os.path.splitext(file_name)[1].lower(), "Plain Text")


# def file_translate(request):
#     if request.method == "POST" and request.FILES.get("file"):
#         file = request.FILES["file"]
#         target_languages = request.POST.getlist("languages")
#         context = request.POST.get("context")  # Get context (App/Web or Content)
#         description = request.POST.get("description")  # Get description
#
#         if not target_languages:
#             return render(request, "translation/upload.html", {"error": "At least one language selection is required."})
#
#         file_path = default_storage.save(file.name, file)
#
#         try:
#             with default_storage.open(file_path, "rb") as f:
#                 content = f.read().decode("utf-8")
#
#                 # Detect file format
#                 file_extension = os.path.splitext(file.name)[1].lower()
#                 file_format_mapping = {
#                     ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
#                     ".po": "PO", ".php": "PHP", ".ini": "INI",
#                     ".xml": "XML", ".csv": "CSV", ".ts": "TS", ".xliff": "XLIFF"
#                 }
#                 file_format = file_format_mapping.get(file_extension, "Plain Text")
#
#                 zip_buffer = io.BytesIO()
#                 with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
#                     for language in target_languages:
#                         translated_content = translate_text(content, language, file_format, context, description)
#
#                         translated_filename = f"{os.path.splitext(file.name)[0]}_{language}{file_extension}"
#                         translated_file_path = os.path.join(settings.MEDIA_ROOT, translated_filename)
#
#                         with open(translated_file_path, "w", encoding="utf-8") as f:
#                             f.write(translated_content)
#
#                         zip_file.write(translated_file_path, translated_filename)
#
#                 zip_buffer.seek(0)
#
#                 response = HttpResponse(zip_buffer.read(), content_type="application/zip")
#                 response["Content-Disposition"] = f'attachment; filename="translated_files.zip"'
#                 return response
#
#         except Exception as e:
#             return render(request, "translation/upload.html", {"error": str(e)})
#
#     return render(request, "translation/upload.html",context={'stripe_key':settings.STRIPE_PUBLISHABLE_KEY})

# @csrf_exempt
# def file_translate(request):
#     if request.method == "POST" and request.FILES.get("file"):
#         file = request.FILES["file"]
#         target_languages = request.POST.getlist("languages")
#         context = request.POST.get("context")
#         description = request.POST.get("description")
#         usage_id = request.POST.get("usage_id")
#         usage = Usage.objects.filter(id=usage_id)
#
#         if not target_languages:
#             return render(request, "translation/upload.html", {"error": "At least one language selection is required."})
#
#         file_path = default_storage.save(file.name, file)
#
#         try:
#             with default_storage.open(file_path, "rb") as f:
#                 content = f.read().decode("utf-8")
#
#                 file_extension = os.path.splitext(file.name)[1].lower()
#                 file_format_mapping = {
#                     ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
#                     ".po": "PO", ".php": "PHP", ".ini": "INI",
#                     ".xml": "XML", ".csv": "CSV", ".ts": "TS", ".xliff": "XLIFF"
#                 }
#                 file_format = file_format_mapping.get(file_extension, "Plain Text")
#
#
#
#                 zip_buffer = io.BytesIO()
#                 futures = []
#                 results = {}
#
#                 with ThreadPoolExecutor() as executor:
#                     for language in target_languages:
#                         futures.append(
#                             executor.submit(
#                                 translate_text,
#                                 content,
#                                 language,
#                                 file_format,
#                                 context,
#                                 description
#                             )
#                         )
#
#                     total_token = 0
#                     for i, future in enumerate(as_completed(futures)):
#                         language = target_languages[i]
#                         translated_content = future.result()
#                         translated_filename = f"{os.path.splitext(file.name)[0]}_{language}{file_extension}"
#                         translated_file_path = os.path.join(settings.MEDIA_ROOT, translated_filename)
#
#                         with open(translated_file_path, "w", encoding="utf-8") as f:
#                             f.write(translated_content.get("content"))
#
#                         results[language] = translated_file_path
#                         total_token += translated_content.get("total_token")
#
#                     if usage.exists():
#                         usage = usage.first()
#                         usage.total_token = total_token
#                         usage.save()
#
#                 with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
#                     for language, path in results.items():
#                         zip_file.write(path, os.path.basename(path))
#
#                 zip_buffer.seek(0)
#                 response = HttpResponse(zip_buffer.read(), content_type="application/zip")
#                 response["Content-Disposition"] = 'attachment; filename="translated_files.zip"'
#                 return response
#
#         except Exception as e:
#             return render(request, "translation/upload.html", {"error": str(e)})
#
#     return render(request, "translation/upload.html", context={'stripe_key': settings.STRIPE_PUBLISHABLE_KEY})

@csrf_exempt
def file_translate(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        target_languages = request.POST.getlist("languages")
        context = request.POST.get("context")
        description = request.POST.get("description")
        usage_id = request.POST.get("usage_id")
        usage = Usage.objects.filter(id=usage_id)

        if not target_languages:
            return render(request, "translation/upload.html", {"error": "At least one language selection is required."})

        file_path = default_storage.save(file.name, file)

        try:
            with default_storage.open(file_path, "rb") as f:
                content = f.read().decode("utf-8")
                file_extension = os.path.splitext(file.name)[1].lower()
                file_format_mapping = {
                    ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
                    ".po": "PO", ".php": "PHP", ".ini": "INI",
                    ".xml": "XML", ".csv": "CSV", ".ts": "TS", ".xliff": "XLIFF"
                }
                file_format = file_format_mapping.get(file_extension, "Plain Text")

                task = translate_and_package.delay(file.name, content, target_languages, file_format, context, description)
                return JsonResponse({"task_id": task.id})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return render(request, "translation/upload.html", context={'stripe_key': settings.STRIPE_PUBLISHABLE_KEY})


def price_estimate(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        target_languages = request.POST.getlist("languages")
        file_path = default_storage.save(file.name, file)
        try:
            with default_storage.open(file_path, "rb") as f:
                content = f.read().decode("utf-8")
                char_count = len(content)
                print('char',char_count)
                text_bytes = count_bytes(content)
                print('bytes',text_bytes)

                if text_bytes > 50000:
                    return JsonResponse({
                        "status": "error",
                        "message": "Your translation content is too large. Maximum allowed is 50,000 bytes per file. Please separate your content into smaller chunks."
                    }, status=400)

                total_bytes = int(text_bytes * len(target_languages))

                if total_bytes > 300000:
                    return JsonResponse({
                        "status": "error",
                        "message": "You have selected too many languages. Please choose up to 3 languages at a time to keep total processing under 300,000 bytes."
                    }, status=400)
                
                if total_bytes <= 300000:
                    if total_bytes <= 10000:
                        price = 1
                    elif total_bytes <= 50000:
                        price = 2
                    elif total_bytes <= 150000:
                        price = 3
                    else:
                        price = 4
                else:
                    return JsonResponse({
                        "status": "error",
                        "message": "Total processing size exceeds limit of 200,000 bytes"
                    }, status=400)
                # if total_bytes >= 1000 and total_bytes <= 2000:
                #     price = 2
                # if total_bytes > 2000 and total_bytes <= 4000:
                #     price = 3
                # else:
                #     price = 4

                usage = Usage.objects.create(price=price, total_bytes=total_bytes,number_of_languages=len(target_languages))
                return JsonResponse({
                    "status": "success",
                    "total_bytes": total_bytes,
                    "text_bytes": text_bytes,
                    "price": round(price, 2),
                    "number_of_languages": len(target_languages),
                    "language_cost": round(text_bytes * 0.0006, 2),
                    "usage_id": usage.id
                })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

# def translation_status(request, task_id):
#     result = AsyncResult(task_id)
#     if result.ready():
#         data = result.get()
#         return JsonResponse({"status": "completed", "download_url": f"/media/{os.path.basename(data['zip_path'])}"})
#     return JsonResponse({"status": "pending"})

def translation_status(request, task_id):
    result = AsyncResult(task_id)

    if result.state == 'PENDING':
        return JsonResponse({
            "status": "pending",
            "progress": 0
        })

    elif result.state == 'PROGRESS':
        return JsonResponse({
            "status": "progress",
            "progress": result.info.get('progress', 0)
        })

    elif result.state == 'SUCCESS':
        data = result.get()
        return JsonResponse({
            "status": "completed",
            "progress": 100,
            "download_url": f"/media/{os.path.basename(data['zip_path'])}"
        })

    elif result.state == 'FAILURE':
        return JsonResponse({
            "status": "failed",
            "progress": 0,
            "error": str(result.result)
        })

    return JsonResponse({
        "status": "unknown",
        "progress": 0
    })

@csrf_exempt
def create_payment_intent(request):
    price = request.POST.get("price")
    amount = int(float(price) * 100)
    print(amount)
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,  # Amount in cents ($10)
            currency="usd",
        )
        return JsonResponse({'client_secret': intent.client_secret})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)