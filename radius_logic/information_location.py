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
