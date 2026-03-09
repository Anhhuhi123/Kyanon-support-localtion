from typing import List, Dict, Any


TRAVEL_TYPE_MAPPING = {
    "solo": "Solo",
    "couple": "Couple", 
    "friends": "Friends",
    "family with kids": "Family with kids",
    "business traveler / free time": "Business traveler / free time",
}


class TravelTypeFilter:
    """Filter POIs based on travel type compatibility score"""
    
    @staticmethod
    def filter_pois_by_travel_type(
        spatial_results: List[Dict[str, Any]],
        travel_type_input: str,
        min_score: int = 50
    ) -> List[str]:
        """Lọc POIs có travel_type score >= min_score"""
        
        key = TRAVEL_TYPE_MAPPING.get(travel_type_input.strip().lower())
        if not key:
            return [poi["id"] for poi in spatial_results if poi.get("id")]
        
        filtered_ids = []
        for poi in spatial_results:
            travel_type = poi.get("travel_type")
            if travel_type and travel_type.get(key, 0) >= min_score:
                filtered_ids.append(poi["id"])
        
        return filtered_ids