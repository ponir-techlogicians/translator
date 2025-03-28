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
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)


def count_tokens(text, model="gpt-4-turbo"):
    """Estimate the token count of a given text for a specific model."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

def count_bytes(text):
    return len(text.encode('utf-8'))

def translate_text(text, target_language, file_format=None, context=None, description=None):
    """Translate entire file content using OpenAI API with context and description"""

    format_instruction = f"The following is a {file_format} file." if file_format else ""
    context_instruction = f"Context: {context}." if context else ""
    description_instruction = f"Description: {description}." if description else ""

    prompt = f"""
    {format_instruction}
    {context_instruction}
    {description_instruction}
    Translate the entire content into {target_language}. Keep the structure unchanged.
    """

    # prompt_tokens = count_tokens(prompt)
    # text_tokens = count_tokens(text)
    # estimated_total_tokens = prompt_tokens + text_tokens
    #
    # print(f"Estimated token usage: {estimated_total_tokens} tokens")

    prompt_bytes = count_tokens(prompt)
    print(prompt_bytes)
    text_bytes = count_tokens(text)
    estimated_total_bytes = prompt_bytes + text_bytes
    print(f"Estimated total bytes: {estimated_total_bytes}")

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": prompt.strip()},
            {"role": "user", "content": text}
        ]
    )
    print(response)



    return response.choices[0].message.content


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


def file_translate(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        target_languages = request.POST.getlist("languages")
        context = request.POST.get("context")  # Get context (App/Web or Content)
        description = request.POST.get("description")  # Get description

        if not target_languages:
            return render(request, "translation/upload.html", {"error": "At least one language selection is required."})

        file_path = default_storage.save(file.name, file)

        try:
            with default_storage.open(file_path, "rb") as f:
                content = f.read().decode("utf-8")

                # Detect file format
                file_extension = os.path.splitext(file.name)[1].lower()
                file_format_mapping = {
                    ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
                    ".po": "PO", ".php": "PHP", ".ini": "INI",
                    ".xml": "XML", ".csv": "CSV", ".ts": "TS", ".xliff": "XLIFF"
                }
                file_format = file_format_mapping.get(file_extension, "Plain Text")

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for language in target_languages:
                        translated_content = translate_text(content, language, file_format, context, description)

                        translated_filename = f"{os.path.splitext(file.name)[0]}_{language}{file_extension}"
                        translated_file_path = os.path.join(settings.MEDIA_ROOT, translated_filename)

                        with open(translated_file_path, "w", encoding="utf-8") as f:
                            f.write(translated_content)

                        zip_file.write(translated_file_path, translated_filename)

                zip_buffer.seek(0)

                response = HttpResponse(zip_buffer.read(), content_type="application/zip")
                response["Content-Disposition"] = f'attachment; filename="translated_files.zip"'
                return response

        except Exception as e:
            return render(request, "translation/upload.html", {"error": str(e)})

    return render(request, "translation/upload.html",context={'stripe_key':settings.STRIPE_PUBLISHABLE_KEY})

def price_estimate(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        target_languages = request.POST.getlist("languages")
        file_path = default_storage.save(file.name, file)
        try:
            with default_storage.open(file_path, "rb") as f:
                content = f.read().decode("utf-8")
                text_bytes = count_tokens(content) + 40
                total_bytes = text_bytes * len(target_languages)
                price = 1
                if total_bytes >= 1000 and total_bytes <= 2000:
                    price = 2
                if total_bytes > 2000 and total_bytes <= 4000:
                    price = 3
                else:
                    price = 4
                return JsonResponse({
                    "status": "success",
                    "total_bytes": total_bytes,
                    "price": price
                })
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)


@csrf_exempt
def create_payment_intent(request):
    price = request.POST.get("price")
    print(price)
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(price)*100,  # Amount in cents ($10)
            currency="usd",
        )
        return JsonResponse({'client_secret': intent.client_secret})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)