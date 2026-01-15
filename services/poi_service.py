import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException
from config.config import Config
from uuid import UUID
from typing import List
import psycopg2.extras
psycopg2.extras.register_uuid()
class PoiService:

    @staticmethod
    def get_visited_pois_by_user(user_id: UUID):
        conn = psycopg2.connect(
            Config.get_db_connection_string(),
            cursor_factory=RealDictCursor
        )
        cursor = conn.cursor()
        print(type(user_id))
        try:
            # 1. Lấy itinerary id
            cursor.execute(
                'SELECT id FROM "UserItinerary" WHERE "userId" = %s',
                (str(user_id),)
            )
            itinerary = cursor.fetchone()
            if not itinerary:
                raise HTTPException(status_code=404, detail="Itinerary not found")

            itinerary_id = itinerary["id"]

            # 2. Lấy danh sách POI đã visit
            cursor.execute(
                'SELECT * FROM "UserItineraryPoi" WHERE "user_itinerary_id" = %s',
                (str(itinerary_id),)
            )
            rows = cursor.fetchall()
            poi_ids = [row["poi_id"] for row in rows]
            return poi_ids
            # return cursor.fetchall()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    

    @staticmethod
    def get_poi_by_ids(poi_ids: list[UUID]):
        if not poi_ids:
            return []
        conn = psycopg2.connect(
            Config.get_db_connection_string(),
            cursor_factory=RealDictCursor
        )
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'SELECT * FROM "PoiClean" WHERE "id" = ANY(%s)',
                (poi_ids,)
            )

            return cursor.fetchall()

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))




