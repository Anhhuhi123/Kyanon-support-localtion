import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import psycopg2
from config.config import Config
from pydantics.poi import PoiRequest
from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/v1/poi", tags=["Poi"])

@router.post("/change")
async def change_data(payload: PoiRequest):
    conn = psycopg2.connect(Config.get_db_connection_string())
    # query = """
    #             SELECT 
    #                 id,
    #                 name,
    #                 poi_type,
    #                 address,
    #                 lat,
    #                 long,
    #                 COALESCE(normalize_stars_reviews, 0.5) AS rating
    #             FROM poi_locations_uuid
    #             WHERE lat BETWEEN %s AND %s
    #               AND long BETWEEN %s AND %s
    #         """
    # cursor = conn.cursor()
    # cursor.execute(query, [min_lat, max_lat, min_lon, max_lon])
    # rows = cursor.fetchall()
    query = """
                SELECT * FROM poi_locations_uuid
            """
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    print(type(rows))
    print(len(rows))
    return {"message": "This is a placeholder for the Poi API endpoint.", "data_received": payload.add}
