"""
Data processing utilities for POI data
- Extract data from Poi table
- Clean data
- Normalize data
- Generate LLM description
"""
import re
import json
import numpy as np
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
load_dotenv()

# ==================== LLM PROMPT ====================

LLM_BASE_PROMPT = """You are an assistant that classifies a Point of Interest (POI) for food & nightlife, specifically Restaurants, Cafes, and Bars.

Your task:
Return a strict JSON object describing the POI. Always include id, poi_type_new, and main_subcategory. Include specialization only when metadata is sufficient.

Allowed values:

1. poi_type_new – must be one of:
   - "Restaurant"
   - "Cafe & Bakery"
   - "Bar"

2. main_subcategory – must be one of:
   - Restaurant: ["Casual Restaurant","Fine Dining","Family Restaurant","Buffet","Fast Food"]
   - Cafe & Bakery: ["Coffee Shop","Tea House","Dessert Cafe","Bakery"]
   - Bar: ["Nightclub","Live Music Venue","Pub & Sports Bar","Rooftop / View Bar"]

3. specialization – must be chosen from:
   - Restaurant: ["Seafood","Sushi","BBQ","Steakhouse","Italian","French","Indian","Japanese","Korean","Thai","Vietnamese","Chinese","Local Food","Vegan/Vegetarian","Fusion"]
   - Cafe & Bakery: ["Pastries","Breakfast/Brunch","Desserts","Vegan Options","Work-friendly","Specialty Coffee","Specialty Tea","Bakery Items", "Pet-friendly"]
   - Bar: ["Nightlife / Party","Chill & Lounge","Live Entertainment","Sports & Social","Scenic View","Craft & Signature"]

Suitability (REQUIRED): Always include the suitability field with Solo, Couple, Friends, Family with kids, and Business traveler / free time percentages (0–100, not required to sum to 100).

Rules:
- Use only allowed categories; do NOT invent new ones.
- If the POI is NOT a Restaurant, Cafe & Bakery, or Bar, set poi_type_new to the actual category from the PoiType metadata.
- Use metadata fields: "Popular for", "Atmosphere", "Offerings", "Highlights", "PoiType", "Crowd", "Dining Options", "Children".
- Always include "id" exactly as provided.
- Always include "poi_type_new".
- Always include "suitability" with Solo, Couple, Friends, Family with kids, Business traveler / free time values.

Output format:
{
  "id": "...",
  "poi_type_new": "...",
  "main_subcategory": "...",
  "specialization": "...",
  "suitability": {
    "Solo": <0-100>,
    "Couple": <0-100>,
    "Friends": <0-100>,
    "Family with kids": <0-100>,
    "Business traveler / free time": <0-100>
  }
}

Now classify the following POI:"""


# ==================== EXTRACT FUNCTIONS ====================

def extract_true_keys(items: Any) -> List[str]:
    """
    Trả về danh sách các key có giá trị True trong một list các dictionary.
    
    Ví dụ:
        items = [{"Wifi": True, "Outdoor seating": False}]
        → ["Wifi"]
    """
    if not isinstance(items, list):
        return []
    return [
        key
        for d in items if isinstance(d, dict)
        for key, value in d.items()
        if value is True
    ]


def to_24h(time_str: str, fallback_am_pm: Optional[str] = None) -> Optional[str]:
    """Convert time string to 24h format"""
    time_str = time_str.strip()

    # If contains AM/PM → direct parse
    if "AM" in time_str.upper() or "PM" in time_str.upper():
        try:
            if ":" in time_str:
                return datetime.strptime(time_str.upper(), "%I:%M %p").strftime("%H:%M")
            else:
                return datetime.strptime(time_str.upper(), "%I %p").strftime("%H:%M")
        except:
            return None

    # If missing AM/PM, but fallback exists
    if fallback_am_pm:
        combined = f"{time_str} {fallback_am_pm}"
        try:
            if ":" in time_str:
                return datetime.strptime(combined, "%I:%M %p").strftime("%H:%M")
            else:
                return datetime.strptime(combined, "%I %p").strftime("%H:%M")
        except:
            pass

    return None


def parse_hours(hours_str: str) -> List[Dict[str, str]]:
    """Parse hours string to list of start/end times"""
    hours_str = hours_str.replace("\u202f", " ").strip()

    # Closed → skip
    if hours_str.lower() == "closed":
        return []

    # Open 24 hours
    if "open 24 hours" in hours_str.lower():
        return [{"start": "00:00", "end": "23:59"}]

    segments = [seg.strip() for seg in hours_str.split(",")]
    results = []

    for segment in segments:
        match = re.match(r"(.*) to (.*)", segment)
        if not match:
            continue

        start_raw, end_raw = match.groups()
        start_raw = start_raw.strip()
        end_raw = end_raw.strip()

        # Determine fallback AM/PM from end if start lacks AM/PM
        fallback = None
        if "AM" in end_raw.upper():
            fallback = "AM"
        if "PM" in end_raw.upper():
            fallback = "PM"

        start_24 = to_24h(start_raw, fallback)
        end_24 = to_24h(end_raw)

        if start_24 and end_24:
            results.append({
                "start": start_24,
                "end": end_24
            })

    return results


def normalize_opening_hours(opening_hours: List[Dict]) -> List[Dict]:
    """Normalize opening hours to standard format"""
    normalized = []

    for item in opening_hours:
        day = item.get("day", "")
        hours = parse_hours(item.get("hours", ""))

        if hours:  # Skip closed days
            normalized.append({"day": day, "hours": hours})

    return normalized


def clean_opening_hours(data: List[List[Dict]]) -> List[List[Dict]]:
    """Clean opening hours data - replace special characters"""
    cleaned = []
    for items in data:
        if not items:
            cleaned.append([])
            continue
        cleaned_items = []
        for i in items:
            cleaned_items.append({
                "day": i.get("day", ""),
                "hours": i.get("hours", "").replace("\u202f", " ")
            })
        cleaned.append(cleaned_items)
    return cleaned


def process_opening_hours(opening_hours_raw: Any) -> List[Dict]:
    """Process raw opening hours to normalized format"""
    if not opening_hours_raw:
        return get_default_opening_hours()
    
    try:
        # Clean and normalize
        cleaned = []
        for item in opening_hours_raw:
            cleaned.append({
                "day": item.get("day", ""),
                "hours": item.get("hours", "").replace("\u202f", " ")
            })
        
        normalized = normalize_opening_hours(cleaned)
        
        if not normalized:
            return get_default_opening_hours()
        
        return normalized
    except:
        return get_default_opening_hours()


def get_default_opening_hours() -> List[Dict]:
    """Return default 24/7 opening hours"""
    return [
        {'day': 'Monday', 'hours': [{'start': '00:00', 'end': '23:59'}]},
        {'day': 'Tuesday', 'hours': [{'start': '00:00', 'end': '23:59'}]},
        {'day': 'Wednesday', 'hours': [{'start': '00:00', 'end': '23:59'}]},
        {'day': 'Thursday', 'hours': [{'start': '00:00', 'end': '23:59'}]},
        {'day': 'Friday', 'hours': [{'start': '00:00', 'end': '23:59'}]},
        {'day': 'Saturday', 'hours': [{'start': '00:00', 'end': '23:59'}]},
        {'day': 'Sunday', 'hours': [{'start': '00:00', 'end': '23:59'}]}
    ]


def extract_poi_data(poi_row: Dict) -> Dict[str, Any]:
    """
    Extract all fields from raw Poi table row
    
    Args:
        poi_row: Dict containing id, content, raw_data, metadata
        
    Returns:
        Dict with extracted fields
    """
    result = {
        "id": poi_row.get("id"),
        "name": None,
        "address": None,
        "lat": None,
        "lon": None,
        "poi_type": None,
        "avg_stars": None,
        "total_reviews": None,
        "opening_hours": [],
        "crowd": "",
        "offerings": "",
        "atmosphere": "",
        "highlights": "",
        "dining_options": "",
        "children": "",
        "accessibility": "",
        "popular_for": ""
    }
    
    # Parse content (có thể là string hoặc dict)
    content = poi_row.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except:
            content = {}
    elif not isinstance(content, dict):
        content = {}
    
    result["name"] = content.get("name")
    result["address"] = content.get("address")
    result["lat"] = content.get("lat")
    result["lon"] = content.get("long")
    
    # Type có thể là list hoặc string
    types = content.get("type")
    if isinstance(types, list):
        result["poi_type"] = ",".join(types)
    else:
        result["poi_type"] = types
    
    # Parse raw_data (có thể là string hoặc dict)
    raw_data = poi_row.get("raw_data")
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except:
            raw_data = {}
    elif not isinstance(raw_data, dict):
        raw_data = {}
    
    google = raw_data.get("google") or {}
    
    result["avg_stars"] = google.get("totalScore")
    result["total_reviews"] = google.get("reviewsCount")
    result["opening_hours"] = process_opening_hours(google.get("openingHours"))
    
    # Parse metadata (có thể là string hoặc dict)
    metadata = poi_row.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except:
            metadata = {}
    elif not isinstance(metadata, dict):
        metadata = {}
    
    additional = metadata.get("additionalInfo") or {}
    
    result["crowd"] = ", ".join(extract_true_keys(additional.get("Crowd")))
    result["offerings"] = ", ".join(extract_true_keys(additional.get("Offerings")))
    result["atmosphere"] = ", ".join(extract_true_keys(additional.get("Atmosphere")))
    result["highlights"] = ", ".join(extract_true_keys(additional.get("Highlights")))
    result["dining_options"] = ", ".join(extract_true_keys(additional.get("Dining options")))
    result["children"] = ", ".join(extract_true_keys(additional.get("Children")))
    result["accessibility"] = ", ".join(extract_true_keys(additional.get("Accessibility")))
    result["popular_for"] = ", ".join(extract_true_keys(additional.get("Popular for")))
    
    return result


def get_poi_features_for_llm(normalized_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare POI features for LLM prompt.
    Chỉ trả về các trường có dữ liệu, bắt buộc phải có poi_type.
    
    Args:
        normalized_data: Dict from normalize_poi_data
        
    Returns:
        Dict with POI features for LLM
    """
    poi_type = normalized_data.get("poi_type")
    if not poi_type:
        return None
    
    # Parse poi_type if it's a comma-separated string
    if isinstance(poi_type, str):
        poi_type_list = [t.strip() for t in poi_type.split(",") if t.strip()]
    else:
        poi_type_list = [poi_type] if poi_type else []
    
    if not poi_type_list:
        return None
    
    result = {
        "id": str(normalized_data.get("id", "")),
        "PoiType": poi_type_list
    }
    
    # Chỉ thêm các trường khác nếu chúng có dữ liệu
    field_mappings = {
        "offerings": "Offerings",
        "highlights": "Highlights",
        "popular_for": "Popular for",
        "atmosphere": "Atmosphere",
        "crowd": "Crowd",
        "dining_options": "Dining Options",
        "children": "Children"
    }
    
    for source_field, target_field in field_mappings.items():
        value = normalized_data.get(source_field, "")
        if value and isinstance(value, str) and value.strip():
            items = [item.strip() for item in value.split(",") if item.strip()]
            if items:
                result[target_field] = items
    
    return result


async def generate_llm_description(normalized_data: Dict[str, Any], client: AsyncOpenAI = None) -> Dict[str, Any]:
    """
    Generate LLM description for a single POI.
    
    Args:
        normalized_data: Dict from normalize_poi_data
        client: AsyncOpenAI client (optional, will create one if not provided)
        
    Returns:
        Dict with LLM generated fields (poi_type_new, main_subcategory, specialization, suitability)
    """
    if client is None:
        client = AsyncOpenAI(api_key = os.getenv("OPENAI_API_KEY"))
    
    features = get_poi_features_for_llm(normalized_data)
    if not features:
        return None
    
    prompt = LLM_BASE_PROMPT + "\n\nPOI:\n" + json.dumps(features, ensure_ascii=False, indent=2)
    
    try:
        response = await client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        
        result = json.loads(response.output_text)
        return result
    except Exception as e:
        print(f"Error generating LLM description for POI {normalized_data.get('id')}: {e}")
        return None


async def generate_llm_descriptions_batch(
    normalized_data_list: List[Dict[str, Any]], 
    batch_size: int = 20,
    client: AsyncOpenAI = None
) -> List[Dict[str, Any]]:
    """
    Generate LLM descriptions for multiple POIs in batches.
    
    Args:
        normalized_data_list: List of dicts from normalize_poi_data
        batch_size: Number of POIs per batch
        client: AsyncOpenAI client
        
    Returns:
        List of LLM results (same order as input)
    """
    import asyncio
    
    if client is None:
        client = AsyncOpenAI()
    
    # Chia thành batches
    batches = [
        normalized_data_list[i:i + batch_size]
        for i in range(0, len(normalized_data_list), batch_size)
    ]
    
    async def process_batch(batch_data: List[Dict]) -> List[Dict]:
        """Process a single batch"""
        pois_text = ""
        for data in batch_data:
            features = get_poi_features_for_llm(data)
            if features:
                pois_text += f"\nPOI:\n{json.dumps(features, ensure_ascii=False, indent=2)}\n"
        
        prompt = (
            LLM_BASE_PROMPT
            + "\n\nBelow is a list of POIs.\n"
            + pois_text
            + "\nReturn a JSON array with one item per POI (same order)."
        )
        
        try:
            response = await client.responses.create(
                model="gpt-4o-mini",
                input=prompt
            )
            return json.loads(response.output_text)
        except Exception as e:
            print(f"Error processing batch: {e}")
            return [None] * len(batch_data)
    
    # Process all batches
    tasks = [process_batch(batch) for batch in batches]
    results_list = await asyncio.gather(*tasks)
    
    # Flatten results
    all_results = []
    for arr in results_list:
        if arr:
            all_results.extend(arr)
        else:
            all_results.extend([None] * batch_size)
    
    return all_results[:len(normalized_data_list)]


# ==================== CLEAN FUNCTIONS ====================

def clean_poi_data(
    extracted_data: Dict[str, Any],
    min_avg_stars: float = 3.0,
    min_total_reviews: int = 1
) -> Dict[str, Any]:
    """
    Clean POI data - handle null values
    
    Args:
        extracted_data: Dict from extract_poi_data
        min_avg_stars: Minimum value for avg_stars when null/0
        min_total_reviews: Minimum value for total_reviews when null/0
        
    Returns:
        Cleaned data dict
    """
    data = extracted_data.copy()
    
    # Clean avg_stars và total_reviews
    avg_stars = data.get("avg_stars")
    total_reviews = data.get("total_reviews")
    
    # Convert to numeric
    try:
        avg_stars = float(avg_stars) if avg_stars is not None else None
    except:
        avg_stars = None
        
    try:
        total_reviews = int(total_reviews) if total_reviews is not None else None
    except:
        total_reviews = None
    
    # Nếu null hoặc 0 thì đưa về giá trị thấp nhất
    if avg_stars is None or avg_stars == 0 or total_reviews is None or total_reviews == 0:
        avg_stars = min_avg_stars
        total_reviews = min_total_reviews
    
    data["avg_stars"] = avg_stars
    data["total_reviews"] = total_reviews
    
    # Clean opening_hours - nếu empty thì dùng default
    if not data.get("opening_hours"):
        data["opening_hours"] = get_default_opening_hours()
    
    return data


# ==================== NORMALIZE FUNCTIONS ====================

def normalize_poi_data(
    cleaned_data: Dict[str, Any],
    min_avg_stars: float = 3.0,
    max_avg_stars: float = 5.0,
    max_total_reviews: int = 10000,
    default_stay_time: float = 30.0
) -> Dict[str, Any]:
    """
    Normalize POI data - calculate normalized scores
    
    Args:
        cleaned_data: Dict from clean_poi_data
        min_avg_stars: Min value for avg_stars normalization
        max_avg_stars: Max value for avg_stars normalization
        max_total_reviews: Max value for total_reviews normalization (log scale)
        default_stay_time: Default stay time in minutes
        
    Returns:
        Normalized data dict with normalize_stars_reviews field
    """
    data = cleaned_data.copy()
    max_total_reviews = max(data.get("total_reviews", 1), max_total_reviews)
    
    avg_stars = data.get("avg_stars", min_avg_stars)
    total_reviews = data.get("total_reviews", 1)
    
    # Add stay_time
    data["stay_time"] = default_stay_time
    
    # Normalize avg_stars using Min-Max Scaling
    if max_avg_stars != min_avg_stars:
        avg_stars_norm = (avg_stars - min_avg_stars) / (max_avg_stars - min_avg_stars)
    else:
        avg_stars_norm = 0.5
    
    # Normalize total_reviews using Log Transform
    if max_total_reviews > 0:
        total_reviews_norm = np.log(total_reviews + 1) / np.log(max_total_reviews + 1)
    else:
        total_reviews_norm = 0.0
    
    # Calculate combined score (60% avg_stars, 40% total_reviews)
    normalize_stars_reviews = round(avg_stars_norm * 0.6 + total_reviews_norm * 0.4, 3)
    
    data["normalize_stars_reviews"] = normalize_stars_reviews
    
    return data


# ==================== MAIN PROCESSING FUNCTION ====================

def process_poi_for_clean_table(
    poi_row: Dict,
    min_avg_stars: float = 1.0,
    min_total_reviews: int = 1,
    max_avg_stars: float = 5.0,
    max_total_reviews: int = 10000,
    default_stay_time: float = 30.0
) -> Dict[str, Any]:
    """
    Complete pipeline: Extract -> Clean -> Normalize
    
    Args:
        poi_row: Raw row from Poi table
        min_avg_stars: Min value for normalization
        min_total_reviews: Min value for normalization
        max_avg_stars: Max value for normalization
        max_total_reviews: Max value for normalization
        default_stay_time: Default stay time
        
    Returns:
        Processed data ready for PoiClean table
    """
    # Step 1: Extract
    extracted = extract_poi_data(poi_row)
    
    # Step 2: Clean
    cleaned = clean_poi_data(extracted, min_avg_stars, min_total_reviews)
    
    # Step 3: Normalize
    normalized = normalize_poi_data(
        cleaned, 
        min_avg_stars, 
        max_avg_stars, 
        max_total_reviews,
        default_stay_time
    )
    
    return normalized
