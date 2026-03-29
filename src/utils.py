import json


def extract_first_json_block(raw_text: str):
    raw_text = raw_text.strip()
    json_start = raw_text.find("{")
    if json_start == -1:
        raise ValueError("No JSON object found in model output.")

    brace_count = 0
    json_end = None

    for i, ch in enumerate(raw_text[json_start:], start=json_start):
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break

    if json_end is None:
        raise ValueError("Could not locate complete JSON block.")

    json_part = raw_text[json_start:json_end]
    markdown_part = raw_text[json_end:].strip()
    return json.loads(json_part), markdown_part
