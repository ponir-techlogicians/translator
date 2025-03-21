import json
import yaml
import openai
import os
import polib
import io
from django.conf import settings
from django.shortcuts import render
from django.core.files.storage import default_storage
from django.http import HttpResponse

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

def translate_text(text, target_language, file_format=None):
    """Translate entire file content using OpenAI API"""
    format_instruction = f"The following is a {file_format} file." if file_format else ""
    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": f"{format_instruction} Translate the entire content into {target_language}. Keep the structure unchanged."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content


def file_translate(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        target_language = request.POST.get("language")

        if not target_language:
            return render(request, "translation/upload.html", {"error": "Language selection is required"})

        file_path = default_storage.save(file.name, file)

        try:
            with default_storage.open(file_path, "rb") as f:
                content = f.read().decode("utf-8")

                # Detect file format
                if file.name.endswith(".json"):
                    file_format = "JSON"
                elif file.name.endswith((".yml", ".yaml")):
                    file_format = "YAML"
                elif file.name.endswith(".po"):
                    file_format = "PO"
                elif file.name.endswith(".php"):
                    file_format = "PHP"
                elif file.name.endswith(".ini"):
                    file_format = "INI"
                elif file.name.endswith(".xml"):
                    file_format = "XML"
                elif file.name.endswith(".csv"):
                    file_format = "CSV"
                elif file.name.endswith(".ts"):
                    file_format = "TS"
                elif file.name.endswith(".xliff"):
                    file_format = "XLIFF"
                else:
                    file_format = "Plain Text"

                # Send the entire content for translation
                translated_content = translate_text(content, target_language, file_format)

                # Save the translated file
                translated_file_path = save_translated_file(file.name, translated_content)

            with open(translated_file_path, "r", encoding="utf-8") as f:
                response = HttpResponse(f.read(), content_type="text/plain")
                response["Content-Disposition"] = f"attachment; filename={os.path.basename(translated_file_path)}"
                return response

        except Exception as e:
            return render(request, "translation/upload.html", {"error": str(e)})

    return render(request, "translation/upload.html")


# def file_translate(request):
#     if request.method == "POST" and request.FILES.get("file"):
#         file = request.FILES["file"]
#         target_language = request.POST.get("language")
#
#         if not target_language:
#             return render(request, "translation/upload.html", {"error": "Language selection is required"})
#
#         file_path = default_storage.save(file.name, file)
#
#         try:
#             with default_storage.open(file_path, "rb") as f:
#                 content = f.read().decode("utf-8")
#
#                 if file.name.endswith(".json"):
#                     data = json.loads(content)
#                     translated_data = translate_dict_values(data, target_language)
#                     translated_content = json.dumps(translated_data, indent=4, ensure_ascii=False)
#
#                 elif file.name.endswith((".yml", ".yaml")):
#                     data = yaml.safe_load(content)
#                     translated_data = translate_dict_values(data, target_language)
#                     translated_content = yaml.dump(translated_data, allow_unicode=True)
#
#                 elif file.name.endswith(".po"):
#                     translated_po = handle_po_file(content, target_language)
#                     # print(translated_po)
#                     translated_content = save_translated_file(file.name, translated_po)
#
#                 else:
#                     translated_content = translate_text(content, target_language)
#
#             # If translated_content is a string, save it as a file
#             if isinstance(translated_content, str):
#                 translated_file_path = save_translated_file(file.name, translated_content)
#
#             with open(translated_file_path, "r", encoding="utf-8") as f:
#                 response = HttpResponse(f.read(), content_type="text/plain")
#                 response["Content-Disposition"] = f"attachment; filename={os.path.basename(translated_file_path)}"
#                 return response
#
#         except Exception as e:
#             return render(request, "translation/upload.html", {"error": str(e)})
#
#     return render(request, "translation/upload.html")
#
#
# def translate_text(text, target_language):
#     """Translate only the given text using OpenAI API"""
#     response = client.chat.completions.create(
#         model="gpt-4-turbo",
#         messages=[
#             {"role": "system", "content": f"Translate the following text to {target_language}"},
#             {"role": "user", "content": str(text)}
#         ]
#     )
#     return response.choices[0].message.content


def translate_dict_values(data, target_language):
    """Recursively translate only the values, not the keys, in a dictionary or list."""
    if isinstance(data, dict):
        return {key: translate_dict_values(value, target_language) for key, value in data.items()}
    elif isinstance(data, list):
        return [translate_dict_values(item, target_language) for item in data]
    elif isinstance(data, str):
        return translate_text(data, target_language)  # Translate only the string values
    return data  # Leave non-string values unchanged


def save_translated_file(original_filename, translated_content):
    """Save the translated content as a new file"""
    new_filename = "translated_" + original_filename
    translated_path = os.path.join(settings.MEDIA_ROOT, new_filename)
    print(translated_content)
    # If the content is POFile (not a string), save using POFile's save method
    if isinstance(translated_content, polib.POFile):
        translated_content.save(translated_path)
    else:
        # For other content like JSON or YAML, write to file normally
        with open(translated_path, "w", encoding="utf-8") as f:
            f.write(translated_content)

    return translated_path


def handle_po_file(content, target_language):
    """Handle PO files by translating msgid values"""

    # Load PO content from a string
    po = polib.pofile(content)  # This should work directly

    # Translate each msgid and store the result in msgstr
    for entry in po:
        if entry.msgid:  # Avoid empty entries
            entry.msgstr = translate_text(entry.msgid, target_language)

    return po  # Return the modified POFile object