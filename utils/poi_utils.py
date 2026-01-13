from utils.json_utils import safe_json_load

def map_poi_record(row: dict) -> dict:
    content = safe_json_load(row.get("content"))
    raw_data = safe_json_load(row.get("raw_data"))

    types = content.get("type")
    poi_type = ",".join(types) if isinstance(types, list) else types

    google = raw_data.get("google", {})

    return {
        "id": row.get("id"),
        "name": content.get("name"),
        "address": content.get("address"),
        "lat": content.get("lat"),
        "lon": content.get("long"),
        "poi_type": poi_type,
        "avg_stars": google.get("totalScore"),
        "total_reviews": google.get("reviewsCount"),
    }
