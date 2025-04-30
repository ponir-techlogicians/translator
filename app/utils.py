import io
import json
import csv
import yaml
import configparser
import xml.etree.ElementTree as ET
from io import StringIO
import re

def chunk_dict(d, chunk_size):
    items = list(d.items())
    for i in range(0, len(items), chunk_size):
        yield dict(items[i:i+chunk_size])


def reconstruct_file_content(data, file_format):
    if file_format in ("json","JSON"):
        return json.dumps(data, ensure_ascii=False, indent=2)

    elif file_format in ("yml", "yaml","YML","YAML"):
        return yaml.dump(data, allow_unicode=True)

    elif file_format in ("ini","INI"):
        parser = configparser.ConfigParser()
        for key, value in data.items():
            section_key = key.split('.')
            section = section_key[0]
            option = '.'.join(section_key[1:])

            if not parser.has_section(section):
                parser.add_section(section)
            parser.set(section, option, value)

        output = io.StringIO()
        parser.write(output)
        return output.getvalue()

    elif file_format in ("csv","CSV"):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['key', 'value'])
        for key, value in data.items():
            writer.writerow([key, value])
        return output.getvalue()

    elif file_format in ['xml', 'ts', 'xliff',"XML","TS","XLIFF"]:
        from xml.etree.ElementTree import Element, tostring
        root = Element('root')
        for key, value in data.items():
            child = Element(key)
            child.text = value
            root.append(child)
        return tostring(root, encoding='unicode')

    elif file_format in ("po","PO"):
        output = []
        for key, value in data.items():
            output.append(f'msgid "{key}"\nmsgstr "{value}"\n')
        return "\n".join(output)

    elif file_format in ("php","PHP"):
        output = "<?php\nreturn [\n"
        for key, value in data.items():
            output += f"    '{key}' => '{value}',\n"
        output += "];"
        return output

    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def parse_file_content(content, file_format):
    if file_format in ("json","JSON"):
        return json.loads(content)

    elif file_format in ("yml", "yaml","YML","YAML"):
        return yaml.safe_load(content)

    elif file_format in ("ini","INI"):
        parser = configparser.ConfigParser()
        parser.read_string(content)
        result = {}
        for section in parser.sections():
            for key, value in parser.items(section):
                result[f"{section}.{key}"] = value
        return result

    elif file_format in ("csv","CSV"):
        # result = {}
        # f = io.StringIO(content)
        # reader = csv.reader(f)
        # headers = next(reader)
        # key_index = headers.index('key')
        # value_index = headers.index('value')
        # for row in reader:
        #     result[row[key_index]] = row[value_index]
        # return result

        result = {}
        f = StringIO(content)
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) >= 2:
                key, value = row[0], row[1]
                result[key] = value
        return result

    elif file_format in ['xml', 'ts', 'xliff',"XML","TS","XLIFF"]:
        # Very basic flat XML parser
        from xml.etree import ElementTree as ET
        root = ET.fromstring(content)
        result = {}
        for elem in root.iter():
            if elem.text and elem.text.strip():
                result[elem.tag] = elem.text.strip()
        return result

    elif file_format in ("po","PO"):
        # Basic .po parser
        result = {}
        lines = content.splitlines()
        msgid, msgstr = None, None
        for line in lines:
            if line.startswith('msgid'):
                msgid = line[6:].strip().strip('"')
            elif line.startswith('msgstr'):
                msgstr = line[7:].strip().strip('"')
                if msgid:
                    result[msgid] = msgstr
                    msgid, msgstr = None, None
        return result

    elif file_format in ("php","PHP"):
        # Assuming PHP array structure like return ['key' => 'value', ...];
        import re
        result = {}
        matches = re.findall(r"'(.*?)'\s*=>\s*'(.*?)'", content)
        for key, value in matches:
            result[key] = value
        return result

    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def flatten_json(y, parent_key='', sep='.'):
    """
    Flatten nested dictionaries into a single dictionary with dot notation.
    Example: {"a": {"b": "c"}} -> {"a.b": "c"}
    """
    items = []
    for k, v in y.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def unflatten_json(d, sep='.'):
    """
    Rebuild nested dictionaries from a flattened dictionary with dot notation.
    """
    result = {}
    for k, v in d.items():
        keys = k.split(sep)
        d_temp = result
        for part in keys[:-1]:
            d_temp = d_temp.setdefault(part, {})
        d_temp[keys[-1]] = v
    return result


def parse_content(content, file_format):
    if file_format in ("json","JSON"):
        data = json.loads(content)
        return flatten_json(data)

    elif file_format in ("yml", "yaml","YML","YAML"):
        data = yaml.safe_load(content)
        return flatten_json(data)

    elif file_format in ("csv","CSV"):
        result = {}
        f = StringIO(content)
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) >= 2:
                key, value = row[0], row[1]
                result[key] = value
        return result

    elif file_format in ("po","PO"):
        # .po files
        result = {}
        entries = re.findall(r'msgid "(.*?)"\s+msgstr "(.*?)"', content, re.DOTALL)
        for msgid, msgstr in entries:
            result[msgid] = msgstr
        return result

    elif file_format in ("php","PHP"):
        # Assumes simple PHP array files like ['key' => 'value']
        result = {}
        matches = re.findall(r"'(.*?)'\s*=>\s*'(.*?)'", content)
        for key, value in matches:
            result[key] = value
        return result

    elif file_format in ("ini","INI"):
        config = configparser.ConfigParser()
        config.read_string(content)
        result = {}
        for section in config.sections():
            for key, value in config.items(section):
                result[f"{section}.{key}"] = value
        return result

    elif file_format in ("xml", "ts", "xliff","XML","TS","XLIFF"):
        result = {}
        tree = ET.ElementTree(ET.fromstring(content))
        for elem in tree.iter():
            if elem.tag in ("source", "translation", "target", "string", "message", "trans-unit"):
                if elem.text and elem.text.strip():
                    result[elem.attrib.get('id', elem.tag)] = elem.text.strip()
        return result

    else:
        raise ValueError(f"Unsupported file format: {file_format}")


def build_content(translated_content, file_format):
    if file_format in ("json","JSON"):
        return json.dumps(unflatten_json(translated_content), ensure_ascii=False, indent=2)

    elif file_format in ("yml", "yaml","YML","YAML"):
        return yaml.safe_dump(unflatten_json(translated_content), allow_unicode=True)

    elif file_format in ("csv", "CSV"):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["key", "value"])
        for key, value in translated_content.items():
            writer.writerow([key, value])
        return output.getvalue()

    elif file_format in ("po", "PO"):
        output = []
        for key, value in translated_content.items():
            output.append(f'msgid "{key}"\nmsgstr "{value}"\n')
        return "\n".join(output)

    elif file_format in ("php", "PHP"):
        output = ["<?php\nreturn ["]
        for key, value in translated_content.items():
            output.append(f"    '{key}' => '{value}',")
        output.append("];")
        return "\n".join(output)

    elif file_format in ("ini", "INI"):
        output = []
        sections = {}
        for full_key, value in translated_content.items():
            if '.' in full_key:
                section, key = full_key.split('.', 1)
            else:
                section, key = 'DEFAULT', full_key
            sections.setdefault(section, []).append((key, value))
        for section, pairs in sections.items():
            output.append(f"[{section}]")
            for key, value in pairs:
                output.append(f"{key} = {value}")
        return "\n".join(output)

    elif file_format in ("xml", "ts", "xliff","XML","TS","XLIFF"):
        root = ET.Element("root")  # you might need a smarter template for real .ts/.xliff
        for key, value in translated_content.items():
            string_elem = ET.SubElement(root, "string", id=key)
            string_elem.text = value
        return ET.tostring(root, encoding="unicode")

    else:
        raise ValueError(f"Unsupported file format: {file_format}")
