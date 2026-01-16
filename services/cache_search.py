"""
Cache Search Service
Quản lý cache cho route metadata và POI data
"""
import json
from typing import Optional, List, Dict, Any
from uuid import UUID
import redis.asyncio as aioredis


class CacheSearchService:
    """Service quản lý cache cho route và POI"""
    
    def __init__(self, redis_client: aioredis.Redis = None):
        """
        Khởi tạo cache service
        
        Args:
            redis_client: Async Redis client
        """
        self.redis_client = redis_client
    
    async def cache_route_metadata(
        self, 
        user_id: UUID, 
        routes: list, 
        semantic_places: list,
        transportation_mode: str = "DRIVING",
        ttl: int = 3600
    ):
        """
        Cache route metadata vào Redis để phục vụ cho update POI
        
        ✅ Chỉ lưu 1 cache duy nhất cho mỗi user_id chứa TẤT CẢ routes
        
        Lưu structure:
        {
            "user_id": "...",
            "transportation_mode": "DRIVING",
            "routes": {
                "1": {
                    "pois": [
                        {"poi_id": "xxx", "category": "Restaurant"},
                        {"poi_id": "yyy", "category": "Culture & heritage"},
                        ...
                    ]
                },
                "2": {...},
                ...
            },
            "available_pois_by_category": {
                "Restaurant": ["id1", "id2", "id3", ...],
                "Culture & heritage": ["id4", "id5", ...],
                ...
            }
        }
        
        Args:
            user_id: UUID của user
            routes: Danh sách routes đã build
            semantic_places: Danh sách POI từ semantic search (có category)
            transportation_mode: Phương tiện di chuyển
            ttl: Time to live (seconds), default 1 hour
        """
        if not self.redis_client:
            print("⚠️  Redis client not initialized")
            return
        
        try:
            # Group POI theo category từ semantic_places
            available_pois_by_category = {}
            for place in semantic_places:
                category = place.get('category')
                poi_id = str(place.get('id'))
                
                if category and poi_id:
                    if category not in available_pois_by_category:
                        available_pois_by_category[category] = []
                    available_pois_by_category[category].append(poi_id)
            
            # Tạo dict chứa TẤT CẢ routes
            routes_data = {}
            for idx, route in enumerate(routes):
                route_id = f"{idx+1}"
                
                # Lấy POIs từ route
                route_pois = []
                for place in route.get('places', []):
                    # Route builder dùng 'place_id' thay vì 'id'
                    poi_id = place.get('place_id') or place.get('id')
                    route_pois.append({
                        "poi_id": str(poi_id),
                        "category": place.get('category', 'Unknown')
                    })
                
                routes_data[route_id] = {
                    "pois": route_pois
                }
            
            # Tạo cache data chứa TẤT CẢ routes
            cache_data = {
                "user_id": str(user_id),
                "transportation_mode": transportation_mode,
                "routes": routes_data,
                "available_pois_by_category": available_pois_by_category
            }
            
            # ✅ Lưu vào Redis với 1 key duy nhất cho user_id
            cache_key = f"route_metadata:{user_id}"
            await self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(cache_data)
            )
            
            print(f"✅ Cached route metadata for user {user_id}: {len(routes)} route(s)")
                
        except Exception as e:
            print(f"⚠️  Failed to cache route metadata: {str(e)}")
    
    async def get_route_metadata(self, user_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Lấy route metadata từ Redis
        
        Args:
            user_id: UUID của user
            
        Returns:
            Dict chứa route metadata hoặc None nếu không tìm thấy
        """
        if not self.redis_client:
            return None
        
        try:
            cache_key = f"route_metadata:{user_id}"
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            print(f"⚠️  Failed to get route metadata: {str(e)}")
            return None
    
    async def cache_poi_data(
        self, 
        poi_id: str, 
        poi_data: Dict[str, Any],
        ttl: int = 3600
    ):
        """
        Cache thông tin POI vào Redis
        
        Args:
            poi_id: ID của POI
            poi_data: Dict chứa thông tin POI
            ttl: Time to live (seconds), default 1 hour
        """
        if not self.redis_client:
            return
        
        try:
            cache_key = f"location:{poi_id}"
            await self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(poi_data)
            )
            
        except Exception as e:
            print(f"⚠️  Failed to cache POI data: {str(e)}")
    
    async def get_poi_data(self, poi_id: str) -> Optional[Dict[str, Any]]:
        """
        Lấy thông tin POI từ Redis
        
        Args:
            poi_id: ID của POI
            
        Returns:
            Dict chứa thông tin POI hoặc None nếu không tìm thấy
        """
        if not self.redis_client:
            return None
        
        try:
            cache_key = f"location:{poi_id}"
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception as e:
            print(f"⚠️  Failed to get POI data: {str(e)}")
            return None    
    async def delete_user_cache(self, user_id: UUID) -> bool:
        """
        Xoá cache của user (route metadata)
        
        Args:
            user_id: UUID của user
            
        Returns:
            True nếu xoá thành công, False nếu không
        """
        if not self.redis_client:
            return False
        
        try:
            cache_key = f"route_metadata:{user_id}"
            result = await self.redis_client.delete(cache_key)
            
            if result > 0:
                print(f"✅ Deleted cache for user {user_id}")
                return True
            else:
                print(f"⚠️  No cache found for user {user_id}")
                return False
            
        except Exception as e:
            print(f"⚠️  Failed to delete cache: {str(e)}")
            return False