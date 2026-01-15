import asyncpg
from fastapi import HTTPException
from uuid import UUID
from typing import List, Optional

class PoiService:
    """Async POI Service với asyncpg pool"""
    
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client = None):
        """
        Khởi tạo POI service với async resources
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client (reserved for future use)
        """
        self.db_pool = db_pool
        self.redis_client = redis_client

    async def get_visited_pois_by_user(self, user_id: UUID) -> List[UUID]:
        """
        Lấy danh sách POI đã visit của user (ASYNC)
        
        Args:
            user_id: UUID của user
            
        Returns:
            List UUID của các POI đã visit
        """
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        try:
            async with self.db_pool.acquire() as conn:
                # 1. Lấy itinerary id
                itinerary = await conn.fetchrow(
                    'SELECT id FROM "UserItinerary" WHERE "userId" = $1',
                    user_id
                )
                
                if not itinerary:
                    raise HTTPException(status_code=404, detail="Itinerary not found")

                itinerary_id = itinerary["id"]

                # 2. Lấy danh sách POI đã visit
                rows = await conn.fetch(
                    'SELECT poi_id FROM "UserItineraryPoi" WHERE "user_itinerary_id" = $1',
                    itinerary_id
                )
                
                poi_ids = [row["poi_id"] for row in rows]
                return poi_ids
                
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_poi_by_ids(self, poi_ids: List[UUID]) -> List[dict]:
        """
        Lấy thông tin POI theo danh sách IDs (ASYNC)
        
        Args:
            poi_ids: List UUID của các POI
            
        Returns:
            List dict chứa thông tin POI
        """
        if not poi_ids:
            return []
        
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    'SELECT * FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                
                # Convert asyncpg.Record to dict
                return [dict(row) for row in rows]

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))




