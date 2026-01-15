"""
Script để kiểm tra cấu trúc cache trong Redis
Hiển thị chi tiết về route metadata cache
"""
import redis
import json
from datetime import timedelta

def format_ttl(seconds):
    """Format TTL thành dạng dễ đọc"""
    if seconds < 0:
        return "No expiration"
    elif seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def format_size(size_bytes):
    """Format size thành dạng dễ đọc"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def check_route_metadata_cache():
    """Kiểm tra và hiển thị cấu trúc cache route metadata"""
    
    print("=" * 80)
    print("🔍 REDIS CACHE STRUCTURE INSPECTOR")
    print("=" * 80)
    
    # Kết nối Redis
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        print("✅ Connected to Redis successfully\n")
    except Exception as e:
        print(f"❌ Cannot connect to Redis: {str(e)}")
        return
    
    # 1. Kiểm tra Route Metadata Cache
    print("\n" + "=" * 80)
    print("📦 ROUTE METADATA CACHE")
    print("=" * 80)
    
    route_keys = r.keys("route_metadata:*")
    
    if not route_keys:
        print("⚠️  No route metadata cache found")
    else:
        print(f"Found {len(route_keys)} user(s) with cached routes:\n")
        
        for idx, key in enumerate(route_keys, 1):
            print(f"{idx}. Key: {key}")
            
            # Lấy TTL
            ttl = r.ttl(key)
            print(f"   └─ TTL: {format_ttl(ttl)}")
            
            # Lấy size
            cache_data = r.get(key)
            if cache_data:
                size = len(cache_data.encode('utf-8'))
                print(f"   └─ Size: {format_size(size)}")
                
                # Parse và hiển thị structure
                try:
                    data = json.loads(cache_data)
                    print(f"   └─ User ID: {data.get('user_id', 'N/A')}")
                    
                    # Hiển thị routes
                    routes = data.get('routes', {})
                    print(f"   └─ Routes: {len(routes)} route(s)")
                    
                    for route_id, route_data in routes.items():
                        pois = route_data.get('pois', [])
                        print(f"      ├─ {route_id}: {len(pois)} POI(s)")
                        
                        # Hiển thị POIs
                        for poi_idx, poi in enumerate(pois, 1):
                            poi_id = poi.get('poi_id', 'N/A')
                            category = poi.get('category', 'N/A')
                            # Truncate POI ID for display
                            short_id = poi_id[:8] + "..." if len(poi_id) > 8 else poi_id
                            print(f"      │  {poi_idx}. {short_id} ({category})")
                    
                    # Hiển thị available POIs by category
                    available_pois = data.get('available_pois_by_category', {})
                    print(f"   └─ Available POIs by Category:")
                    
                    if available_pois:
                        for category, poi_ids in available_pois.items():
                            print(f"      ├─ {category}: {len(poi_ids)} POI(s)")
                    else:
                        print(f"      └─ (empty)")
                    
                    # Hiển thị sample JSON structure (collapsed)
                    print(f"\n   📄 Sample Structure:")
                    print(f"   {{")
                    print(f"     \"user_id\": \"{data.get('user_id', 'N/A')}\",")
                    print(f"     \"routes\": {{ ... {len(routes)} route(s) ... }},")
                    print(f"     \"available_pois_by_category\": {{ ... {len(available_pois)} category(ies) ... }}")
                    print(f"   }}")
                    
                except json.JSONDecodeError:
                    print(f"   └─ ⚠️  Invalid JSON data")
            
            print()
    
    # 2. Kiểm tra Location/POI Cache
    print("\n" + "=" * 80)
    print("📍 LOCATION/POI CACHE")
    print("=" * 80)
    
    location_keys = r.keys("location:*")
    
    if not location_keys:
        print("⚠️  No location cache found")
    else:
        print(f"Found {len(location_keys)} cached location(s)")
        print(f"Sample keys (first 5):")
        for key in location_keys[:5]:
            ttl = r.ttl(key)
            print(f"  • {key} (TTL: {format_ttl(ttl)})")
        
        if len(location_keys) > 5:
            print(f"  ... and {len(location_keys) - 5} more")
    
    # 3. Kiểm tra H3 Cell Cache
    print("\n" + "=" * 80)
    print("🔷 H3 CELL CACHE")
    print("=" * 80)
    
    h3_keys = r.keys("poi:h3:*")
    
    if not h3_keys:
        print("⚠️  No H3 cell cache found")
    else:
        print(f"Found {len(h3_keys)} cached H3 cell(s)")
        print(f"Sample keys (first 5):")
        for key in h3_keys[:5]:
            ttl = r.ttl(key)
            print(f"  • {key} (TTL: {format_ttl(ttl)})")
        
        if len(h3_keys) > 5:
            print(f"  ... and {len(h3_keys) - 5} more")
    
    # 4. Tổng hợp thống kê
    print("\n" + "=" * 80)
    print("📊 CACHE STATISTICS")
    print("=" * 80)
    
    total_keys = len(route_keys) + len(location_keys) + len(h3_keys)
    
    print(f"Total cached keys: {total_keys}")
    print(f"  ├─ Route metadata: {len(route_keys)}")
    print(f"  ├─ Location/POI: {len(location_keys)}")
    print(f"  └─ H3 cells: {len(h3_keys)}")
    
    # Memory info
    try:
        info = r.info('memory')
        used_memory = info.get('used_memory', 0)
        used_memory_human = info.get('used_memory_human', 'N/A')
        print(f"\nRedis memory usage: {used_memory_human}")
    except:
        pass
    
    print("\n" + "=" * 80)
    print("✅ Cache inspection completed!")
    print("=" * 80)


def check_specific_user_cache(user_id: str):
    """Kiểm tra cache chi tiết của 1 user cụ thể"""
    
    print("=" * 80)
    print(f"🔍 CHECKING CACHE FOR USER: {user_id}")
    print("=" * 80)
    
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
    except Exception as e:
        print(f"❌ Cannot connect to Redis: {str(e)}")
        return
    
    cache_key = f"route_metadata:{user_id}"
    
    if not r.exists(cache_key):
        print(f"⚠️  No cache found for user: {user_id}")
        return
    
    # Lấy data
    cache_data = r.get(cache_key)
    ttl = r.ttl(cache_key)
    
    print(f"\n✅ Cache found!")
    print(f"Key: {cache_key}")
    print(f"TTL: {format_ttl(ttl)}")
    print(f"Size: {format_size(len(cache_data.encode('utf-8')))}")
    
    # Parse và hiển thị full JSON
    try:
        data = json.loads(cache_data)
        print(f"\n📄 Full JSON Structure:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(f"⚠️  Invalid JSON data")
        print(f"Raw data: {cache_data[:200]}...")


if __name__ == "__main__":
    import sys
    
    # Nếu có argument là user_id, check specific user
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        check_specific_user_cache(user_id)
    else:
        # Nếu không có argument, check toàn bộ cache
        check_route_metadata_cache()
