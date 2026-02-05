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
    Hỗ trợ 2 dạng dữ liệu:
    1) list[str]
       ["Wifi", "Outdoor seating"]
       → ["Wifi", "Outdoor seating"]

    2) list[dict]
       [{"Wifi": True, "Outdoor seating": False}]
       → ["Wifi"]
    """
    if not isinstance(items, list):
        return []

    # Case 1: list of string
    if all(isinstance(x, str) for x in items):
        return items

    # Case 2: list of dict (True/False)
    result = []
    for d in items:
        if isinstance(d, dict):
            for key, value in d.items():
                if value is True:
                    result.append(key)
    return result



def new_process_poi_for_description(poi_row: Dict) -> Dict[str, Any]:
    """
    Extract all fields from raw Poi table row
    
    Args:
        poi_row: Dict containing id, content, raw_data, metadata
        
    Returns:
        Dict with extracted fields
    """
    result = {
        "id": poi_row.get("id"),
        "poi_type": poi_row.get("poi_type"),
        "crowd": "",
        "offerings": "",
        "atmosphere": "",
        "highlights": "",
        "dining_options": "",
        "children": "",
        "accessibility": "",
        "popular_for": "",
    }
    # Read metadata from the input row, metadata may be a dict, a JSON string, or Non
    metadata = poi_row.get("metadata")
    # If metadata is a string, attempt to parse it as JSON
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except:
            metadata = {}
    elif not isinstance(metadata, dict):
        metadata = {}
    
    result["crowd"] = ", ".join(extract_true_keys(metadata.get("Crowd")))
    result["offerings"] = ", ".join(extract_true_keys(metadata.get("Offerings")))
    result["atmosphere"] = ", ".join(extract_true_keys(metadata.get("Atmosphere")))
    result["highlights"] = ", ".join(extract_true_keys(metadata.get("Highlights")))
    result["dining_options"] = ", ".join(extract_true_keys(metadata.get("Dining options")))
    result["children"] = ", ".join(extract_true_keys(metadata.get("Children")))
    result["accessibility"] = ", ".join(extract_true_keys(metadata.get("Accessibility")))
    result["popular_for"] = ", ".join(extract_true_keys(metadata.get("Popular for")))
    
    return result
