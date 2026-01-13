import json

def safe_json_load(value):
    # print("value", value)
    if isinstance(value, str):
        try:
            return json.loads(value)
            print("a")
        except Exception:
            print("b")
            return {}
    return value if isinstance(value, dict) else {}
