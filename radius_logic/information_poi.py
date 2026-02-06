"""
Information Location Service (Async Version)
Module để lấy thông tin đầy đủ của location từ database bằng ID
Sử dụng Async Connection Pool và Redis Caching để tối ưu hiệu năng
"""
import asyncpg
import redis.asyncio as aioredis
import json
import uuid
from typing import List, Dict, Any, Optional
from uuid import UUID
from config.config import Config
from utils.time_utils import TimeUtils
from .route.route_config import RouteConfig

class LocationInfoService:
    """Service để query thông tin location từ database với async pool và Redis caching"""
    
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client: aioredis.Redis = None, cache_ttl: int = None):
        """
        Khởi tạo service với async connection pool và Redis client
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client
            cache_ttl: Time-to-live cho cache (seconds), default từ Config
        """
        self.db_pool = db_pool
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl or Config.REDIS_CACHE_TTL

    @staticmethod
    def _is_valid_uuid(location_id: str) -> bool:
        """Validate UUID format"""
        try:
            uuid.UUID(str(location_id))
            return True
        except (ValueError, TypeError):
            return False

    def _get_cache_key(self, location_id: str) -> str:
        """Tạo cache key cho location"""
        return f"location:{location_id}"
    
    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Lấy data từ Redis cache (async)"""
        if not self.redis_client:
            return None
        try:
            cached = await self.redis_client.get(cache_key)
            if cached is not None:
                return json.loads(cached)
        except Exception as e:
            print(f"Cache read error: {e}")
        return None
    
    async def _set_cache(self, cache_key: str, data: Dict[str, Any]):
        """Lưu data vào Redis cache (async)"""
        if not self.redis_client:
            return
        try:
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(data)
            )
        except Exception as e:
            print(f"Cache write error: {e}")
    
    async def _get_many_from_cache(self, cache_keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """Lấy nhiều items từ cache cùng lúc (pipeline async)"""
        if not self.redis_client or not cache_keys:
            return {}
        
        try:
            # Sử dụng pipeline để fetch nhiều keys cùng lúc
            pipe = self.redis_client.pipeline()
            for key in cache_keys:
                pipe.get(key)
            
            cached_values = await pipe.execute()
            
            # Parse kết quả
            result = {}
            for key, value in zip(cache_keys, cached_values):
                if value:
                    location_id = key.split(':', 1)[1]  # Extract ID from "location:xxx"
                    result[location_id] = json.loads(value)
            
            return result
        except Exception as e:
            print(f"Cache batch read error: {e}")
            return {}
    
    async def _set_many_cache(self, data_dict: Dict[str, Dict[str, Any]]):
        """Lưu nhiều items vào cache cùng lúc (pipeline async)"""
        if not self.redis_client or not data_dict:
            return
        
        try:
            pipe = self.redis_client.pipeline()
            for location_id, data in data_dict.items():
                cache_key = self._get_cache_key(location_id)
                pipe.setex(cache_key, self.cache_ttl, json.dumps(data))
            await pipe.execute()
        except Exception as e:
            print(f"Cache batch write error: {e}")
    
    async def get_location_by_id(self, location_id: str) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin location theo ID với Redis caching (async)
        
        Args:
            location_id: ID của location
            
        Returns:
            Dict chứa thông tin location hoặc None nếu không tìm thấy
        """

        # Validate UUID trước khi xử lý
        if not self._is_valid_uuid(location_id):
            return None

        # Check cache trước
        cache_key = self._get_cache_key(location_id)
        cached = await self._get_from_cache(cache_key)
        if cached is not None:  # Check is not None
            if cached == {}:  # Negative cache hit
                return None
            return cached  # Positive cache hit
        
        # Query từ database nếu cache miss
        if not self.db_pool:
            return None
            
        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT 
                        id,
                        name,
                        lat,
                        lon,
                        address,
                        poi_type,
                        normalize_stars_reviews,
                        stay_time,
                        open_hours
                    FROM public."PoiClean"
                    WHERE id = $1
                """
                
                row = await conn.fetchrow(query, location_id)
                
                if not row:
                    # Negative caching: cache empty dict để tránh query lại
                    await self._set_cache(cache_key, {})
                    return None
                
                stay_time = row['stay_time'] if row['stay_time'] is not None else RouteConfig.DEFAULT_STAY_TIME

                result = {
                    "id": str(row['id']),  # Convert UUID to string
                    "name": row['name'],
                    "lat": row['lat'],
                    "lon": row['lon'],
                    "address": row['address'],
                    "poi_type": row['poi_type'],
                    "rating": row['normalize_stars_reviews'],
                    "stay_time": float(stay_time),
                    "open_hours": TimeUtils.normalize_open_hours(row['open_hours'])
                }
                
                # Lưu vào cache
                await self._set_cache(cache_key, result)
                
                return result
                
        except Exception as e:
            print(f"Error getting location {location_id}: {e}")
            return None
    
    async def get_locations_by_ids(self, location_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Lấy thông tin nhiều locations theo danh sách IDs với Redis caching (async)
        
        Tối ưu:
        - Check cache trước (batch get với pipeline)
        - Chỉ query DB cho các IDs chưa có trong cache
        - Cache kết quả mới (batch set với pipeline)
        
        Args:
            location_ids: List các ID cần query
            
        Returns:
            Dict mapping {id: location_info}
        """
        if not location_ids:
            return {}

        # Validate và filter chỉ lấy valid UUIDs
        valid_ids = [lid for lid in location_ids if self._is_valid_uuid(lid)]
        
        if not valid_ids:
            return {}
        
        # Bước 1: Check cache cho tất cả IDs (batch get async)
        cache_keys = [self._get_cache_key(lid) for lid in valid_ids]
        cached_results = await self._get_many_from_cache(cache_keys)
        
        # Bước 2: Tìm IDs chưa có trong cache
        missing_ids = [lid for lid in valid_ids if lid not in cached_results]
        
        # Nếu tất cả đều có trong cache, return luôn
        if not missing_ids:
            return cached_results
        
        # Bước 3: Query DB chỉ cho missing IDs (1 query duy nhất, async)
        if not self.db_pool:
            return cached_results
            
        try:
            async with self.db_pool.acquire() as conn:
                # Sử dụng ANY() - hiệu quả cho array lớn
                query = """
                    SELECT 
                        id,
                        name,
                        lat,
                        lon,
                        address,
                        poi_type,
                        poi_type_clean,
                        main_subcategory,
                        specialization,
                        normalize_stars_reviews,
                        stay_time,
                        open_hours
                    FROM public."PoiClean"
                    WHERE id = ANY($1::uuid[])
                """
                
                rows = await conn.fetch(query, missing_ids)
                
                # Bước 4: Parse kết quả từ DB
                
                db_results = {}
                for row in rows:
                    location_id = str(row['id'])  # Convert UUID to string
                    stay_time = row['stay_time'] if row['stay_time'] is not None else RouteConfig.DEFAULT_STAY_TIME
                    db_results[location_id] = {
                        "id": location_id,
                        "name": row['name'],
                        "lat": row['lat'],
                        "lon": row['lon'],
                        "address": row['address'],
                        "poi_type": row['poi_type'],
                        "poi_type_clean": row['poi_type_clean'],
                        "main_subcategory": row['main_subcategory'],
                        "specialization": row['specialization'],
                        "rating": row['normalize_stars_reviews'],
                        "stay_time": float(stay_time),
                        "open_hours": TimeUtils.normalize_open_hours(row['open_hours'])
                    }
                
                # Bước 5: Negative caching cho các IDs không tìm thấy
                found_ids = set(db_results.keys())
                not_found_ids = [lid for lid in missing_ids if lid not in found_ids]
                negative_cache_data = {lid: {} for lid in not_found_ids}
                
                # Cache cả positive và negative results
                all_cache_data = {**db_results, **negative_cache_data}
                if all_cache_data:
                    await self._set_many_cache(all_cache_data)  
                
                # Bước 6: Merge cached + DB results (filter out negative cache)
                # Chỉ merge positive cache và DB results
                positive_cached = {k: v for k, v in cached_results.items() if v != {}}
                final_results = {**positive_cached, **db_results}
            
                return final_results
                
        except Exception as e:
            print(f"Error getting locations batch: {e}")
            # Fallback: return cached results nếu có lỗi DB
            return cached_results
    
    async def get_visited_pois_by_user(self, user_id: UUID) -> List[UUID]:
        """
        Lấy danh sách POI đã visit của user
        
        Args:
            user_id: UUID của user
            
        Returns:
            List UUID của các POI đã visit
        """
        if not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                # 1. Lấy itinerary id
                itinerary = await conn.fetchrow(
                    'SELECT id FROM "UserItinerary" WHERE "userId" = $1',
                    user_id
                )
                
                if not itinerary:
                    return []

                itinerary_id = itinerary["id"]

                # 2. Lấy danh sách POI đã visit
                rows = await conn.fetch(
                    'SELECT poi_id FROM "UserItineraryPoi" WHERE "user_itinerary_id" = $1',
                    itinerary_id
                )
                
                poi_ids = [row["poi_id"] for row in rows]
                return poi_ids
                
        except Exception as e:
            print(f"Error getting visited POIs for user {user_id}: {e}")
            return []
    
    async def get_poi_by_ids(self, poi_ids: List[UUID]) -> List[dict]:
        """
        Lấy thông tin POI theo danh sách IDs
        
        Args:
            poi_ids: List UUID của các POI
            
        Returns:
            List dict chứa thông tin POI
        """
        if not poi_ids or not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    'SELECT * FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                
                return [dict(row) for row in rows]

        except Exception as e:
            print(f"Error getting POI by IDs: {e}")
            return []
    
    async def upsert_poi_clean(self, data: Dict[str, Any]):
        """
        Insert or Update POI data vào bảng PoiClean
        
        Args:
            data: Dict chứa thông tin POI cần insert/update
        """
        if not self.db_pool:
            raise Exception("Database pool not initialized")

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
            open_hours,
            created_at,
            "updatedAt",
            "deletedAt"
        )
        VALUES (
            $1, $2, $3, $4, $5,
            ST_SetSRID(ST_MakePoint($6, $7), 4326),
            $8, $9, $10, $11,
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
            open_hours = EXCLUDED.open_hours,
            "updatedAt" = NOW();
        """

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                upsert_sql,
                data.get("id"),
                data.get("name"),
                data.get("address"),
                data.get("lat"),
                data.get("lon"),
                data.get("lon"),
                data.get("lat"),
                data.get("poi_type"),
                data.get("avg_stars"),
                data.get("total_reviews"),
                opening_hours_json
            )
    
    async def update_poi_clean_from_llm(self, poi_id: UUID, poi_data: Dict[str, Any]):
        """
        Update PoiClean table từ kết quả LLM
        
        Args:
            poi_id: UUID của POI
            poi_data: Dict chứa data từ LLM
        """
        if not self.db_pool:
            raise Exception("Database pool not initialized")
        
        poi_type_clean = poi_data.get('poi_type_new')
        main_subcategory = poi_data.get('main_subcategory')
        specialization = poi_data.get('specialization')
        suitability = poi_data.get('suitability')
        stay_time = poi_data.get('stay_time')

        # Convert suitability dict to JSON string
        suitability_json = json.dumps(suitability) if suitability else None
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''UPDATE "PoiClean"
                SET poi_type_clean = $1,
                    main_subcategory = $2,
                    specialization = $3,
                    travel_type = $4,
                    stay_time = $5,
                    "updatedAt" = NOW()
                WHERE id = $6''',
                poi_type_clean,
                main_subcategory,
                specialization,
                suitability_json,
                stay_time,
                poi_id
            )
    
    async def delete_pois(self, poi_ids: List[UUID]) -> Dict[str, Any]:
        """
        Xóa POI khỏi bảng PoiClean theo danh sách IDs
        
        Args:
            poi_ids: List UUID của các POI cần xóa
            
        Returns:
            Dict chứa thông tin về số lượng deleted và not found
        """
        if not self.db_pool or not poi_ids:
            return {
                "deleted_count": 0,
                "not_found_ids": []
            }

        try:
            async with self.db_pool.acquire() as conn:
                # Lấy các id tồn tại
                existing_rows = await conn.fetch(
                    'SELECT id FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                    poi_ids,
                )
                existing_ids = [row["id"] for row in existing_rows]
                not_found_ids = [str(pid) for pid in poi_ids if pid not in existing_ids]

                deleted_count = 0
                if existing_ids:
                    result = await conn.execute(
                        'DELETE FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                        existing_ids,
                    )
                    deleted_count = int(result.split()[-1]) if result else len(existing_ids)

                return {
                    "deleted_count": deleted_count,
                    "not_found_ids": not_found_ids
                }

        except Exception as e:
            print(f"Error deleting POIs: {e}")
            return {
                "deleted_count": 0,
                "not_found_ids": [str(pid) for pid in poi_ids]
            }
    
    async def normalize_data(self) -> bool:
        """
        Normalize normalize_stars_reviews cho toàn bộ POI bằng SQL
        
        Returns:
            True nếu thành công, False nếu có lỗi
        """
        if not self.db_pool:
            return False

        sql = """
        WITH stats AS (
            SELECT
                MIN(avg_stars) AS min_avg_stars,
                MAX(avg_stars) AS max_avg_stars,
                MAX(total_reviews) AS max_total_reviews
            FROM "PoiClean"
            WHERE "deletedAt" IS NULL
        )
        UPDATE "PoiClean" p
        SET
            normalize_stars_reviews = ROUND(
                (
                    (
                        CASE
                            WHEN s.max_avg_stars != s.min_avg_stars
                            THEN
                                (COALESCE(p.avg_stars, s.min_avg_stars) - s.min_avg_stars)
                                / (s.max_avg_stars - s.min_avg_stars)
                            ELSE
                                0.5
                        END
                    ) * 0.6
                    +
                    (
                        CASE
                            WHEN s.max_total_reviews > 0
                            THEN
                                LN(COALESCE(p.total_reviews, 1) + 1)
                                / LN(s.max_total_reviews + 1)
                            ELSE
                                0
                        END
                    ) * 0.4
                )::numeric
            , 3),
            "updatedAt" = NOW()
        FROM stats s
        WHERE p."deletedAt" IS NULL;
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(sql)
            return True

        except Exception as e:
            print(f"Error normalizing data: {e}")
            return False
    
    async def get_poi_from_source_table(self, poi_ids: List[UUID]) -> List[dict]:
        """
        Lấy data từ bảng Poi (source table)
        
        Args:
            poi_ids: List UUID của các POI
            
        Returns:
            List dict chứa thông tin POI từ bảng Poi
        """
        if not poi_ids or not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    'SELECT id, content, raw_data, metadata FROM "Poi" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                return [dict(row) for row in rows]

        except Exception as e:
            print(f"Error getting POI from source table: {e}")
            return []
    
    async def get_min_avg_stars(self) -> float:
        """
        Lấy giá trị MIN của avg_stars từ PoiClean
        
        Returns:
            Giá trị min của avg_stars, default 1.0 nếu không có
        """
        if not self.db_pool:
            return 1.0
        
        try:
            async with self.db_pool.acquire() as conn:
                min_row = await conn.fetchrow(
                    'SELECT MIN(avg_stars) AS min_avg_stars FROM "PoiClean" WHERE avg_stars IS NOT NULL AND "deletedAt" IS NULL'
                )
                return min_row["min_avg_stars"] if min_row and min_row["min_avg_stars"] else 1.0

        except Exception as e:
            print(f"Error getting min avg_stars: {e}")
            return 1.0
