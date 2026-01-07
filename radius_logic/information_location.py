"""
Information Location Service
Module để lấy thông tin đầy đủ của location từ database bằng ID
Sử dụng Connection Pooling và Redis Caching để tối ưu hiệu năng
"""
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values
from typing import List, Dict, Any, Optional
import redis
import json
from config.config import Config

class LocationInfoService:
    """Service để query thông tin location từ database với connection pooling và Redis caching"""
    
    # Class-level connection pool (shared across instances)
    _connection_pool = None
    _pool_initialized = False
    _redis_client = None
    
    def __init__(self, db_connection_string: Optional[str] = None, cache_ttl: int = None):
        """
        Khởi tạo service với connection pooling và Redis caching
        
        Args:
            db_connection_string: PostgreSQL connection string (nếu None, dùng từ Config)
            cache_ttl: Time-to-live cho cache (seconds), default từ Config
        """
        self.db_connection_string = db_connection_string or Config.get_db_connection_string()
        self.cache_ttl = cache_ttl or Config.REDIS_CACHE_TTL
        
        # Khởi tạo connection pool nếu chưa có
        if not LocationInfoService._pool_initialized:
            self._initialize_pool()
        
        # Khởi tạo Redis client nếu chưa có
        if LocationInfoService._redis_client is None:
            self._initialize_redis()
    
    def _initialize_pool(self):
        """Khởi tạo connection pool"""
        try:
            # Parse connection string thành dict
            conn_params = {}
            for param in self.db_connection_string.split():
                key, value = param.split('=', 1)
                conn_params[key] = value
            
            # Disable SSL nếu không cần thiết (giảm latency)
            if 'sslmode' not in conn_params:
                conn_params['sslmode'] = 'prefer'  # hoặc 'disable' nếu local network
            
            # Tăng số connection để giảm contention
            LocationInfoService._connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=10,  # Tăng từ 5 lên 10
                maxconn=30,  # Tăng từ 20 lên 30
                **conn_params
            )
            LocationInfoService._pool_initialized = True
            print(f"✓ PostgreSQL connection pool initialized (10-30 connections, sslmode={conn_params.get('sslmode')})")
        except Exception as e:
            print(f"Error initializing connection pool: {e}")
            raise
    
    def _initialize_redis(self):
        """Khởi tạo Redis client cho caching"""
        try:
            LocationInfoService._redis_client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_keepalive=True,
                health_check_interval=30
            )
            # Test connection
            LocationInfoService._redis_client.ping()
            print(f"✓ Redis cache initialized ({Config.REDIS_HOST}:{Config.REDIS_PORT})")
        except Exception as e:
            print(f"⚠ Redis not available, caching disabled: {e}")
            LocationInfoService._redis_client = None
    
    def _get_cache_key(self, location_id: str) -> str:
        """Tạo cache key cho location"""
        return f"location:{location_id}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Lấy data từ Redis cache"""
        if not self._redis_client:
            return None
        try:
            cached = self._redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"Cache read error: {e}")
        return None
    
    def _set_cache(self, cache_key: str, data: Dict[str, Any]):
        """Lưu data vào Redis cache"""
        if not self._redis_client:
            return
        try:
            self._redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(data)
            )
        except Exception as e:
            print(f"Cache write error: {e}")
    
    def _get_many_from_cache(self, cache_keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """Lấy nhiều items từ cache cùng lúc (pipeline)"""
        if not self._redis_client or not cache_keys:
            return {}
        
        try:
            # Sử dụng pipeline để fetch nhiều keys cùng lúc
            pipe = self._redis_client.pipeline()
            for key in cache_keys:
                pipe.get(key)
            
            cached_values = pipe.execute()
            
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
    
    def _set_many_cache(self, data_dict: Dict[str, Dict[str, Any]]):
        """Lưu nhiều items vào cache cùng lúc (pipeline)"""
        if not self._redis_client or not data_dict:
            return
        
        try:
            pipe = self._redis_client.pipeline()
            for location_id, data in data_dict.items():
                cache_key = self._get_cache_key(location_id)
                pipe.setex(cache_key, self.cache_ttl, json.dumps(data))
            pipe.execute()
        except Exception as e:
            print(f"Cache batch write error: {e}")
    
    def _get_connection(self):
        """Lấy connection từ pool"""
        if LocationInfoService._connection_pool:
            return LocationInfoService._connection_pool.getconn()
        else:
            # Fallback: tạo connection thường nếu pool không khả dụng
            return psycopg2.connect(self.db_connection_string)
    
    def _return_connection(self, conn):
        """Trả connection về pool"""
        if LocationInfoService._connection_pool:
            LocationInfoService._connection_pool.putconn(conn)
        else:
            conn.close()
    
    def get_location_by_id(self, location_id: str) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin location theo ID (với caching)
        
        Args:
            location_id: ID của location
            
        Returns:
            Dict chứa thông tin location hoặc None nếu không tìm thấy
        """
        # Kiểm tra cache trước
        cache_key = self._get_cache_key(location_id)
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        # Nếu không có trong cache, query DB
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    id,
                    name,
                    lat,
                    lon,
                    address,
                    poi_type,
                    normalize_stars_reviews
                FROM public."PoiClean"
                WHERE id = %s::uuid
            """
            
            cursor.execute(query, (location_id,))
            row = cursor.fetchone()
            
            cursor.close()
            
            if not row:
                return None
            
            result = {
                "id": row[0],
                "name": row[1],
                "lat": row[2],
                "lon": row[3],
                "address": row[4],
                "poi_type": row[5],
                "rating": row[6]
            }
            
            # Lưu vào cache
            self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            print(f"Error getting location {location_id}: {e}")
            return None
        finally:
            if conn:
                self._return_connection(conn)
    
    def get_locations_by_ids(self, location_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Lấy thông tin nhiều locations theo danh sách IDs với Redis caching
        
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
        
        # Bước 1: Check cache cho tất cả IDs (batch get)
        cache_keys = [self._get_cache_key(lid) for lid in location_ids]
        cached_results = self._get_many_from_cache(cache_keys)
        # Bước 2: Tìm IDs chưa có trong cache
        missing_ids = [lid for lid in location_ids if lid not in cached_results]
        
        # Nếu tất cả đều có trong cache, return luôn
        if not missing_ids:
            return cached_results
        
        # Bước 3: Query DB chỉ cho missing IDs (1 query duy nhất)
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Sử dụng ANY() - hiệu quả cho array lớn
            query = """
                SELECT 
                    id,
                    name,
                    lat,
                    lon,
                    address,
                    poi_type,
                    normalize_stars_reviews
                FROM public."PoiClean"
                WHERE id = ANY(%s::uuid[])
            """
            
            cursor.execute(query, (missing_ids,))
            rows = cursor.fetchall()
            
            cursor.close()
            
            # Bước 4: Parse kết quả từ DB
            db_results = {}
            for row in rows:
                db_results[row[0]] = {
                    "id": row[0],
                    "name": row[1],
                    "lat": row[2],
                    "lon": row[3],
                    "address": row[4],
                    "poi_type": row[5],
                    "rating": row[6]
                }
            
            # Bước 5: Cache kết quả mới (batch set)
            # print("db_results", db_results)
            if db_results:
                self._set_many_cache(db_results)
            
            # Bước 6: Merge cached + DB results
            final_results = {**cached_results, **db_results}
            # print("final_results", final_results)
        
            return final_results
            
        except Exception as e:
            print(f"Error getting locations batch: {e}")
            # Fallback: return cached results nếu có lỗi DB
            return cached_results
        finally:
            if conn:
                self._return_connection(conn)
    
    @classmethod
    def close_pool(cls):
        """Đóng connection pool khi shutdown application"""
        if cls._connection_pool:
            cls._connection_pool.closeall()
            cls._pool_initialized = False
            print("✓ PostgreSQL connection pool closed")
