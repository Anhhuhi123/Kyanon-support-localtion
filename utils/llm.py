
"""
Data processing utilities for POI data
- Extract data from Poi table
- Generate LLM description
"""
import json
import pandas as pd
from typing import List, Optional, Dict, Any
from uuid import UUID


# ===============================
# PROCESS ONE BATCH
# ===============================

async def process_batch(batch_ids, index, poi_map, base_prompt, client):
    prompt = build_prompt(batch_ids, poi_map, base_prompt)

    try:
        response = await client.responses.create(
            model="gpt-5-mini",
            input=prompt
        )

        # Xử lý response theo cấu trúc của OpenAI API
        text = None
        
        # Cách 1: response.output_text (nếu có)
        if hasattr(response, 'output_text') and response.output_text:
            text = response.output_text
        # Cách 2: response.output[0].content[0].text
        elif hasattr(response, 'output') and response.output:
            try:
                text = response.output[0].content[0].text
            except (IndexError, AttributeError, TypeError):
                pass
        # Cách 3: response.choices[0].message.content (chat completions format)
        elif hasattr(response, 'choices') and response.choices:
            try:
                text = response.choices[0].message.content
            except (IndexError, AttributeError, TypeError):
                pass
        
        if not text:
            print(f"[Batch {index}] Empty response from LLM")
            return [None] * len(batch_ids)
        
        # Clean markdown wrapper trước khi parse JSON
        cleaned_text = clean_json_response(text)
        
        # Parse JSON từ text
        result = json.loads(cleaned_text)
        return result
        
    except json.JSONDecodeError as e:
        print(f"[Batch {index}] JSON parse error: {e}")
        print(f"[Batch {index}] Raw text: {text[:500] if text else 'None'}")
        return [None] * len(batch_ids)
    except Exception as e:
        print(f"[Batch {index}] Error: {e}")
        return [None] * len(batch_ids)



# ===============================
# HELPER FUNCTIONS
# ===============================

def _parse_comma_separated(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []

    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]

    try:
        return list(value)
    except Exception:
        return []


def get_poi_features_by_id(poi_id, poi_map):
    poi = poi_map.get(poi_id)
    if not poi:
        return None

    poi_type = _parse_comma_separated(poi.get("poi_type"))
    if not poi_type:
        return None

    result = {
        "id": str(poi_id),
        "PoiType": poi_type
    }

    field_map = {
        "Offerings": "offerings",
        "Highlights": "highlights",
        "Popular for": "popular_for",
        "Atmosphere": "atmosphere",
        "Crowd": "crowd",
        "Dining Options": "dining_options",
        "Children": "children"
    }

    for out_key, in_key in field_map.items():
        values = _parse_comma_separated(poi.get(in_key))
        if values:
            result[out_key] = values

    return result

# ===============================
# PROMPT BUILDER
# ===============================

def build_prompt(batch_ids, poi_map, base_prompt):
    pois_text = ""

    for poi_id in batch_ids:
        features = get_poi_features_by_id(poi_id, poi_map)

        if features is None:
            pois_text += f'\nPOI:\n{{"id": "{poi_id}", "PoiType": []}}\n'
        else:
            pois_text += (
                "\nPOI:\n"
                + json.dumps(features, ensure_ascii=False, indent=2)
                + "\n"
            )

    return (
        base_prompt
        + "\n\nBelow is a list of POIs.\n"
        + pois_text
        + "\nReturn a JSON array with one item per POI (same order)."
    )

# ===============================
# HELPER: Clean JSON from markdown
# ===============================

def clean_json_response(text: str) -> str:
    """
    Remove markdown code blocks from LLM response.
    Example: ```json\n{...}\n``` -> {...}
    """
    if not text:
        return text
    
    text = text.strip()
    
    # Remove ```json or ``` at the start
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    # Remove ``` at the end
    if text.endswith("```"):
        text = text[:-3]
    
    return text.strip()


