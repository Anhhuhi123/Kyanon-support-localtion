"""
Information Location Service
Module để lấy thông tin đầy đủ của location từ database bằng ID
Sử dụng Connection Pooling để tối ưu hiệu năng
"""
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values
from typing import List, Dict, Any, Optional
from config.config import Config

class LocationInfoService:
    """Service để query thông tin location từ database với connection pooling"""
    
    # Class-level connection pool (shared across instances)
    _connection_pool = None
    _pool_initialized = False
    
    def __init__(self, db_connection_string: Optional[str] = None):
        """
        Khởi tạo service với connection pooling
        
        Args:
            db_connection_string: PostgreSQL connection string (nếu None, dùng từ Config)
        """
        self.db_connection_string = db_connection_string or Config.get_db_connection_string()
        
        # Khởi tạo connection pool nếu chưa có
        if not LocationInfoService._pool_initialized:
            self._initialize_pool()
    
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
        Lấy thông tin location theo ID
        
        Args:
            location_id: ID của location
            
        Returns:
            Dict chứa thông tin location hoặc None nếu không tìm thấy
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    id,
                    name,
                    lat,
                    long,
                    address,
                    poi_type,
                    normalize_stars_reviews
                FROM poi_locations
                WHERE id = %s
            """
            
            cursor.execute(query, (location_id,))
            row = cursor.fetchone()
            
            cursor.close()
            
            if not row:
                return None
            
            return {
                "id": row[0],
                "name": row[1],
                "lat": row[2],
                "lon": row[3],
                "address": row[4],
                "poi_type": row[5],
                "rating": row[6]  # normalize_stars_reviews -> rating
            }
            
        except Exception as e:
            print(f"Error getting location {location_id}: {e}")
            return None
        finally:
            if conn:
                self._return_connection(conn)
    
    def get_locations_by_ids(self, location_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Lấy thông tin nhiều locations theo danh sách IDs (batch query)
        Sử dụng ANY() để query hiệu quả hơn IN clause
        
        Args:
            location_ids: List các ID cần query
            
        Returns:
            Dict mapping {id: location_info}
        """
        if not location_ids:
            return {}
        
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Sử dụng ANY() thay vì IN() - hiệu quả hơn cho array lớn
            query = """
                SELECT 
                    id,
                    name,
                    lat,
                    long,
                    address,
                    poi_type,
                    normalize_stars_reviews
                FROM poi_locations
                WHERE id = ANY(%s)
            """
            
            cursor.execute(query, (location_ids,))
            rows = cursor.fetchall()
            
            cursor.close()
            
            # Tạo dictionary mapping id -> location info
            result = {}
            for row in rows:
                result[row[0]] = {
                    "id": row[0],
                    "name": row[1],
                    "lat": row[2],
                    "lon": row[3],
                    "address": row[4],
                    "poi_type": row[5],
                    "rating": row[6]  # normalize_stars_reviews -> rating
                }
            
            return result
            
        except Exception as e:
            print(f"Error getting locations batch: {e}")
            return {}
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
