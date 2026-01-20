"""
Data processing utilities for POI data
- Extract data from Poi table
- Clean data
- Normalize data
"""
import re
import json
import numpy as np
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

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


def process_poi_for_description(poi_row: Dict):
    return extract_poi_data(poi_row)

def extract_poi_data(poi_row: Dict, default_stay_time: float = 30.0) -> Dict[str, Any]:
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
    result["stay_time"] = default_stay_time
    
    return result


def process_ingest_to_poi_clean(
    poi_row: Dict,
    default_stay_time: float = 30.0,
) -> Dict[str, Any]:
 
    # Step 1: Extract
    extracted = extract_poi_data(poi_row,default_stay_time)
    
    return extracted