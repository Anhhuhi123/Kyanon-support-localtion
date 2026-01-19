"""
H3 + Redis Based Radius Search (Async Version)
Tìm kiếm địa điểm sử dụng H3 hexagons và Redis cache để tối ưu performance
"""
import h3
import json
import math
import asyncpg
import redis.asyncio as aioredis
from typing import List, Dict, Any, Tuple, Set, Optional
from config.config import Config
from utils.time_utils import TimeUtils

class H3RadiusSearch:
    """
    Tìm kiếm địa điểm sử dụng H3 hexagonal indexing và Redis cache (ASYNC)
    
    Workflow:
    1. Chuyển (lat, lon) thành H3 cell ở resolution từ Config
    2. Tìm k-ring (các cell lân cận) dựa trên transportation mode
    3. Lấy POI từ Redis cache cho các cells (async)
    4. Nếu cache miss hoặc không đủ POI, query PostgreSQL (async) và update cache
    """
    
    def __init__(self, db_pool: Optional[asyncpg.Pool] = None, redis_client: Optional[aioredis.Redis] = None):
        """
        Khởi tạo H3RadiusSearch với async db pool và redis client
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client
        """
        self.db_pool = db_pool
        self.redis_client = redis_client
        
        # Lấy config từ Config class
        self.h3_resolution = Config.H3_RESOLUTION
        self.cache_ttl = Config.REDIS_CACHE_TTL
        
    def calculate_distance_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Tính khoảng cách Haversine (km)
        
        Args:
            lat1, lon1: Tọa độ điểm 1
            lat2, lon2: Tọa độ điểm 2
            
        Returns:
            Khoảng cách (km)
        """
        R = 6371  # Bán kính trái đất (km)
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def get_k_ring_for_mode(self, transportation_mode: str) -> int:
        """
        Lấy k-ring value từ Config dựa trên transportation mode
        
        Args:
            transportation_mode: Loại phương tiện (WALKING, BICYCLING, ...)
            
        Returns:
            Số k (số vòng hexagon) từ config
        """
        config = Config.get_transportation_config(transportation_mode)
        return config.get("h3_k_ring", 1)
    
    def get_h3_coverage_radius(self, k: int) -> float:
        """
        Tính bán kính coverage thực tế (meters) của k-ring H3 cells
        
        Args:
            k: K-ring value (số lớp hexagon)
            
        Returns:
            Bán kính coverage (meters)
        """
        # Lấy edge length của H3 cell ở resolution hiện tại (km)
        edge_length_km = h3.edge_length(self.h3_resolution, unit='km')
        
        # Coverage radius ≈ edge_length × k × 1.5 (hệ số hình học hexagon)
        # Thêm 10% margin để chắc chắn
        coverage_radius_km = edge_length_km * k * 1.5 * 1.1
        
        return coverage_radius_km * 1000  # Convert to meters
    
    def get_bbox_margin(self, k: int) -> float:
        """
        Tính margin cho bbox dựa trên H3 cell size và k-ring
        
        Args:
            k: K-ring value
            
        Returns:
            Margin (degrees) cho bbox
        """
        # Edge length (km) → margin (degrees)
        # 1 degree ≈ 111km ở xích đạo
        edge_length_km = h3.edge_length(self.h3_resolution, unit='km')
        
        # Margin = (k + 1) × edge_length × 1.2 (safety factor)
        margin_km = (k + 1) * edge_length_km * 1.2
        margin_deg = margin_km / 111.0
        
        return margin_deg
    
    def get_redis_key(self, h3_index: str) -> str:
        """
        Tạo Redis key cho H3 cell, chỉ dựa trên resolution và h3_index
        (không phụ thuộc k vì POI thuộc cell không thay đổi theo k)
        Ví dụ: "poi:h3:res9:8928308280fffff"
        
        Args:
            h3_index: H3 cell index
            
        Returns:
            Redis key string
        """
        return f"poi:h3:res{self.h3_resolution}:{h3_index}"
    
    async def get_pois_from_cache(self, h3_indices: Set[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Lấy POI từ Redis cache cho nhiều H3 cells (ASYNC)
        
        Args:
            h3_indices: Set các H3 cell indices
            
        Returns:
            Dict mapping h3_index -> list of POIs (None nếu cache miss, [] nếu cell rỗng)
        """
        result = {}
        
        if not self.redis_client:
            # Fallback: no cache available
            return {idx: None for idx in h3_indices}
        
        # Convert Set to List để giữ thứ tự
        idx_list = list(h3_indices)
        
        # Tạo list keys tương ứng với idx_list
        keys = [self.get_redis_key(idx) for idx in idx_list]
        
        # ✅ Sử dụng MGET để batch get tất cả keys cùng lúc
        cached_values = await self.redis_client.mget(keys)
        
        # Parse kết quả
        for h3_index, cached in zip(idx_list, cached_values):
            if cached is not None:  # Cache hit (kể cả "[]")
                result[h3_index] = json.loads(cached)
            else:  # Cache miss
                result[h3_index] = None
        
        return result
    
    async def query_pois_for_h3_cells(self, h3_indices: Set[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Query POI từ PostgreSQL cho các H3 cells và cache vào Redis (ASYNC)
        ✅ FIX BUG: Mỗi POI chỉ thuộc 1 H3 cell duy nhất (dựa vào geo_to_h3)
        
        Args:
            h3_indices: Set các H3 cell indices
            
        Returns:
            Dict mapping h3_index -> list of POIs
        """
        if not h3_indices or not self.db_pool:
            return {}
        
        async with self.db_pool.acquire() as conn:
            try:
                # Tìm bbox toàn cục từ TẤT CẢ centers của k-ring cells
                all_centers = []
                for h3_index in h3_indices:
                    center_lat, center_lon = h3.h3_to_geo(h3_index)
                    all_centers.append((center_lat, center_lon))
                
                # ✅ FIX: Tính margin dựa trên kích thước 1 H3 cell (không cần ước lượng k)
                # Vì bbox đã được xây từ min/max của TẤT CẢ centers, margin chỉ cần bù kích thước 1 cell
                edge_km = h3.edge_length(self.h3_resolution, unit='km')
                # Margin = edge_length * 1.05 (5% safety) / 111km (1 degree)
                margin_deg = (edge_km * 1.05) / 111.0
                
                min_lat = min(c[0] for c in all_centers) - margin_deg
                max_lat = max(c[0] for c in all_centers) + margin_deg
                min_lon = min(c[1] for c in all_centers) - margin_deg
                max_lon = max(c[1] for c in all_centers) + margin_deg
                
                # Single batch query for all POIs in global bbox
                query = """
                    SELECT 
                        id,
                        name,
                        poi_type,
                        address,
                        lat,
                        lon,
                        COALESCE(normalize_stars_reviews, 0.5) AS rating,
                        open_hours,
                        poi_type_clean,
                        main_subcategory,
                        specialization
                    FROM public."PoiClean"
                    WHERE lat BETWEEN $1 AND $2
                      AND lon BETWEEN $3 AND $4
                """
                
                bbox_size_lat = max_lat - min_lat
                bbox_size_lon = max_lon - min_lon
                print(f"  📊 Batch query for {len(h3_indices)} cells (bbox: {bbox_size_lat:.4f}° × {bbox_size_lon:.4f}°, ~{bbox_size_lat*111:.1f}km × {bbox_size_lon*111:.1f}km)")
                
                rows = await conn.fetch(query, min_lat, max_lat, min_lon, max_lon)
                print(f"  ✓ Found {len(rows)} total POIs in global bbox")
                
                # ✅ FIX: Phân phối POI vào ĐÚNG H3 cell của nó
                result = {h3_idx: [] for h3_idx in h3_indices}
                distributed_count = 0
                
                for row in rows:
                    
                    poi = {
                        "id": str(row['id']),  # Convert UUID to string for JSON serialization
                        "name": row['name'],
                        "poi_type": row['poi_type'],
                        "poi_type_clean": row['poi_type_clean'],
                        "main_subcategory": row['main_subcategory'],
                        "specialization": row['specialization'],
                        "address": row['address'],
                        "lat": row['lat'],
                        "lon": row['lon'],
                        "rating": round(float(row['rating'] or 0.5), 3),
                        "open_hours": TimeUtils.normalize_open_hours(row['open_hours'])
                    }
                    
                    # Tính H3 cell mà POI này thuộc về
                    poi_h3 = h3.geo_to_h3(poi["lat"], poi["lon"], self.h3_resolution)
                    
                    # Chỉ thêm vào cell của POI NẾU cell đó nằm trong tập cần query
                    if poi_h3 in result:
                        result[poi_h3].append(poi)
                        distributed_count += 1
                
                # Cache ALL cells (cả cells rỗng) để tránh query lại
                if self.redis_client:
                    cached_count = 0
                    cells_with_pois = 0
                    
                    for h3_index, pois in result.items():
                        if pois:
                            cells_with_pois += 1
                            
                        # Cache TẤT CẢ cells (kể cả rỗng) để lần sau không query lại
                        key = self.get_redis_key(h3_index)
                        await self.redis_client.setex(key, self.cache_ttl, json.dumps(pois))
                        cached_count += 1
                    
                    print(f"  📊 Distribution: {cells_with_pois}/{len(h3_indices)} cells have POIs, total {distributed_count} POIs")
                    print(f"  💾 Cached {cached_count} cells with POIs")
                
                return result
                
            except Exception as e:
                print(f"❌ Error querying POIs: {e}")
                raise
    
    async def search_locations(
        self,
        latitude: float,
        longitude: float,
        transportation_mode: str
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        ✅ FIX BUG #3: Tìm kiếm địa điểm sử dụng H3 + Redis cache (ASYNC)
        Search 1 lần với k-ring cố định theo mode, không loop radius
        
        Args:
            latitude: Vĩ độ
            longitude: Kinh độ
            transportation_mode: Phương tiện
            
        Returns:
            Tuple (results, coverage_radius):
            - results: List POI với distance_meters (sorted by distance)
            - coverage_radius: Bán kính coverage thực tế của k-ring (meters)
        """
        # 1. Lấy k-ring cho transportation mode
        k = self.get_k_ring_for_mode(transportation_mode)
        
        # 2. Tính coverage radius thực tế của k-ring này
        coverage_radius = self.get_h3_coverage_radius(k)
        
        # 3. Lấy H3 index của điểm trung tâm
        center_h3 = h3.geo_to_h3(latitude, longitude, self.h3_resolution)
        
        # 4. Lấy tất cả H3 cells trong k-ring
        h3_indices = h3.k_ring(center_h3, k)
        
        print(f"🔍 H3 Search: mode={transportation_mode}, k-ring={k}, cells={len(h3_indices)}, coverage_radius={coverage_radius:.0f}m")
        
        # 5. Lấy POI từ cache (async)
        cached_pois = await self.get_pois_from_cache(h3_indices)
        # Cache hit = value không None (kể cả [] rỗng)
        cache_hits = sum(1 for v in cached_pois.values() if v is not None)
        cache_misses = len(h3_indices) - cache_hits
        
        print(f"📦 Cache: {cache_hits} hits, {cache_misses} misses")
        
        # 6. Query POI cho cache misses (cells với value = None) (async)
        miss_indices = {idx for idx, pois in cached_pois.items() if pois is None}
        if miss_indices:
            fresh_pois = await self.query_pois_for_h3_cells(miss_indices)
            cached_pois.update(fresh_pois)
        
        # 7. Merge tất cả POI và tính khoảng cách
        all_pois = {}  # Dict[poi_id, poi_data] để loại trùng
        
        for h3_idx, pois in cached_pois.items():
            for poi in pois:
                poi_id = poi["id"]
                if poi_id not in all_pois:
                    # Tính khoảng cách Haversine
                    distance_km = self.calculate_distance_haversine(
                        latitude, longitude,
                        poi["lat"], poi["lon"]
                    )
                    distance_m = distance_km * 1000
                    
                    # Chỉ thêm nếu trong coverage radius
                    if distance_m <= coverage_radius:
                        poi["distance_meters"] = round(distance_m, 2)
                        all_pois[poi_id] = poi
        
        # Debug: chi tiết cells và POIs
        cells_with_data = sum(1 for pois in cached_pois.values() if pois)
        total_raw_pois = sum(len(pois) for pois in cached_pois.values())
        print(f"📍 Cells with data: {cells_with_data}/{len(h3_indices)}, Raw POIs: {total_raw_pois}, Unique after dedupe: {len(all_pois)}")
        
        # 8. Sắp xếp theo khoảng cách
        results = sorted(all_pois.values(), key=lambda x: x["distance_meters"])
        
        print(f"🎯 Final: {len(results)} POIs within k-ring {k} (coverage_radius={coverage_radius:.0f}m)")
        
        return results, int(coverage_radius)
