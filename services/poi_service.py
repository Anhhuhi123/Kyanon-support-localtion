import asyncpg
import json
from fastapi import HTTPException
from uuid import UUID
from typing import List, Optional, Dict, Any

from utils.data_processing import process_poi_for_clean_table


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
                    # User chưa có itinerary → return empty list thay vì raise exception
                    return []

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

    
    async def get_max_total_reviews(self) -> int:
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    'SELECT MAX(total_reviews) AS max_reviews FROM "PoiClean"'
                )

                # row["max_reviews"] có thể là None nếu bảng rỗng
                return row["max_reviews"] or 0

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        

    async def add_new_poi(self, poi_ids: List[UUID], max_total_reviews: int) -> Dict[str, Any]:
        """
        Lấy thông tin POI từ bảng Poi theo danh sách IDs,
        sau đó clean, normalize và insert/update vào bảng PoiClean.
        
        Quy trình:
        1. Lấy data từ bảng Poi theo id
        2. Clean data (xử lý null values, opening_hours)
        3. Normalize data (tính normalize_stars_reviews)
        4. Insert/Update vào bảng PoiClean
        
        Args:
            poi_ids: List UUID của các POI cần xử lý
            
        Returns:
            Dict chứa kết quả: success_count, failed_count, failed_ids
        """
        
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        if not poi_ids:
            return {
                "success_count": 0,
                "failed_count": 0,
                "failed_ids": [],
                "message": "No POI IDs provided"
            }
        
        success_count = 0
        failed_count = 0
        failed_ids = []
        
        try:
            async with self.db_pool.acquire() as conn:
                # Step 1: Lấy data từ bảng Poi
                rows = await conn.fetch(
                    'SELECT id, content, raw_data, metadata FROM "Poi" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                
                if not rows:
                    return {
                        "success_count": 0,
                        "failed_count": len(poi_ids),
                        "failed_ids": [str(pid) for pid in poi_ids],
                        "message": "No POI found with provided IDs"
                    }
                
                # Step 2 & 3: Process each POI (Extract -> Clean -> Normalize)
                for row in rows:
                    try:
                        poi_data = dict(row)
                        
                        # Process data through pipeline
                        processed_data = process_poi_for_clean_table(
                            poi_row=poi_data,
                            min_avg_stars=1.0,
                            min_total_reviews=1,
                            max_avg_stars=5.0,
                            max_total_reviews=max_total_reviews,
                            default_stay_time=30.0
                        ) 
                        
                        # Validate required fields
                        if not processed_data.get("lat") or not processed_data.get("lon"):
                            failed_count += 1
                            failed_ids.append(str(poi_data.get("id")))
                            continue
                        
                        # Step 4: Insert/Update vào bảng PoiClean
                        await self._upsert_poi_clean(conn, processed_data)
                        success_count += 1
                        
                    except Exception as e:
                        failed_count += 1
                        failed_ids.append(str(row.get("id")))
                        print(f"Error processing POI {row.get('id')}: {e}")
                
                return {
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_ids": failed_ids,
                    "message": f"Processed {success_count} POIs successfully, {failed_count} failed"
                }
                # return processed_data

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _upsert_poi_clean(self, conn: asyncpg.Connection, data: Dict[str, Any]):
        """
        Insert or Update POI data vào bảng PoiClean
        
        Args:
            conn: Database connection
            data: Processed POI data
        """
        # Convert opening_hours to JSON string
        opening_hours_json = json.dumps(data.get("opening_hours", []))
        
        upsert_sql = """
        INSERT INTO public."PoiClean" (
            id,
            name,
            address,
            lat,
            lon,
            geom,
            poi_type,
            avg_stars,
            total_reviews,
            stay_time,
            normalize_stars_reviews,
            open_hours,
            created_at,
            "updatedAt",
            "deletedAt"
        )
        VALUES (
            $1, $2, $3, $4, $5,
            ST_SetSRID(ST_MakePoint($6, $7), 4326),
            $8, $9, $10, $11, $12, $13,
            NOW(),
            NOW(),
            NULL
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            address = EXCLUDED.address,
            lat = EXCLUDED.lat,
            lon = EXCLUDED.lon,
            geom = EXCLUDED.geom,
            poi_type = EXCLUDED.poi_type,
            avg_stars = EXCLUDED.avg_stars,
            total_reviews = EXCLUDED.total_reviews,
            stay_time = EXCLUDED.stay_time,
            normalize_stars_reviews = EXCLUDED.normalize_stars_reviews,
            open_hours = EXCLUDED.open_hours,
            "updatedAt" = NOW();
        """
        
        await conn.execute(
            upsert_sql,
            data.get("id"),                          # $1: id
            data.get("name"),                        # $2: name
            data.get("address"),                     # $3: address
            data.get("lat"),                         # $4: lat
            data.get("lon"),                         # $5: lon
            data.get("lon"),                         # $6: x for ST_MakePoint
            data.get("lat"),                         # $7: y for ST_MakePoint
            data.get("poi_type"),                    # $8: poi_type
            data.get("avg_stars"),                   # $9: avg_stars
            data.get("total_reviews"),               # $10: total_reviews
            data.get("stay_time"),                   # $11: stay_time
            data.get("normalize_stars_reviews"),     # $12: normalize_stars_reviews
            opening_hours_json                       # $13: open_hours
        )



    async def update_existing_poi(self, poi_ids: List[UUID], max_total_reviews: int) -> Dict[str, Any]:
        """
        Cập nhật thông tin POI đã tồn tại trong bảng PoiClean.
        Lấy data mới từ bảng Poi, clean, normalize và update vào PoiClean.
        
        Quy trình:
        1. Kiểm tra POI có tồn tại trong PoiClean không
        2. Lấy data mới từ bảng Poi theo id
        3. Clean data (xử lý null values, opening_hours)
        4. Normalize data (tính normalize_stars_reviews)
        5. Update vào bảng PoiClean
        
        Args:
            poi_ids: List UUID của các POI cần cập nhật
            max_total_reviews: Giá trị max total_reviews để normalize
            
        Returns:
            Dict chứa kết quả: success_count, failed_count, failed_ids, not_found_ids
        """
        
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        if not poi_ids:
            return {
                "success_count": 0,
                "failed_count": 0,
                "failed_ids": [],
                "not_found_ids": [],
                "message": "No POI IDs provided"
            }
        
        success_count = 0
        failed_count = 0
        failed_ids = []
        not_found_ids = []
        
        try:
            async with self.db_pool.acquire() as conn:
                # Step 1: Kiểm tra POI có tồn tại trong PoiClean không
                existing_rows = await conn.fetch(
                    'SELECT id FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                existing_ids = [row["id"] for row in existing_rows]
                not_found_ids = [str(pid) for pid in poi_ids if pid not in existing_ids]
                
                if not existing_ids:
                    return {
                        "success_count": 0,
                        "failed_count": 0,
                        "failed_ids": [],
                        "not_found_ids": not_found_ids,
                        "message": "No POI found in PoiClean with provided IDs"
                    }
                
                # Step 2: Lấy data mới từ bảng Poi
                rows = await conn.fetch(
                    'SELECT id, content, raw_data, metadata FROM "Poi" WHERE "id" = ANY($1::uuid[])',
                    existing_ids
                )
                
                if not rows:
                    return {
                        "success_count": 0,
                        "failed_count": len(existing_ids),
                        "failed_ids": [str(pid) for pid in existing_ids],
                        "not_found_ids": not_found_ids,
                        "message": "No POI found in Poi table with provided IDs"
                    }
                
                # Step 3 & 4: Process each POI (Extract -> Clean -> Normalize)
                for row in rows:
                    try:
                        poi_data = dict(row)
                        
                        # Process data through pipeline
                        processed_data = process_poi_for_clean_table(
                            poi_row=poi_data,
                            min_avg_stars=1.0,
                            min_total_reviews=1,
                            max_avg_stars=5.0,
                            max_total_reviews=max_total_reviews,
                            default_stay_time=30.0
                        ) 
                        
                        # Validate required fields
                        if not processed_data.get("lat") or not processed_data.get("lon"):
                            failed_count += 1
                            failed_ids.append(str(poi_data.get("id")))
                            continue
                        
                        # Step 5: Update vào bảng PoiClean (sử dụng upsert)
                        await self._upsert_poi_clean(conn, processed_data)
                        success_count += 1
                        
                    except Exception as e:
                        failed_count += 1
                        failed_ids.append(str(row.get("id")))
                        print(f"Error processing POI {row.get('id')}: {e}")
                
                return {
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_ids": failed_ids,
                    "not_found_ids": not_found_ids,
                    "message": f"Updated {success_count} POIs successfully, {failed_count} failed, {len(not_found_ids)} not found in PoiClean"
                }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    async def delete_poi(self, poi_ids: List[UUID]) -> Dict[str, Any]:
        """
        Xóa POI từ bảng PoiClean theo danh sách IDs.
        
        Args:
            poi_ids: List UUID của các POI cần xóa
            
        Returns:
            Dict chứa kết quả: deleted_count, not_found_ids
        """
        
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        if not poi_ids:
            return {
                "deleted_count": 0,
                "not_found_ids": [],
                "message": "No POI IDs provided"
            }
        
        try:
            async with self.db_pool.acquire() as conn:
                # Kiểm tra POI có tồn tại trong PoiClean không
                existing_rows = await conn.fetch(
                    'SELECT id FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                existing_ids = [row["id"] for row in existing_rows]
                not_found_ids = [str(pid) for pid in poi_ids if pid not in existing_ids]
                
                if existing_ids:
                    # Xóa các POI tồn tại
                    await conn.execute(
                        'DELETE FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                        existing_ids
                    )
                
                return {
                    "deleted_count": len(existing_ids),
                    "not_found_ids": not_found_ids,
                    "message": f"Deleted {len(existing_ids)} POIs, {len(not_found_ids)} not found"
                }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


