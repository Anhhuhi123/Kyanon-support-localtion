"""
Test script cho update POI endpoint
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1/route"

def test_route_search_and_update():
    """
    Test workflow:
    1. Tạo route mới với route search
    2. Lấy route_id và poi_id từ kết quả
    3. Update một POI trong route
    """
    
    print("=" * 80)
    print("TEST 1: Route Search - Tạo route và cache metadata")
    print("=" * 80)
    
    # 1. Tạo route
    route_request = {
        "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
        "latitude": 10.774087,
        "longitude": 106.703535,
        "transportation_mode": "WALKING",
        "semantic_query": "Food & Local Flavours",
        "current_time": "2026-01-15T12:00:00",
        "max_time_minutes": 180,
        "target_places": 5,
        "max_routes": 1,
        "top_k_semantic": 10
    }
    
    print("\n📤 Sending route search request...")
    print(f"Request: {json.dumps(route_request, indent=2)}")
    
    response = requests.post(f"{BASE_URL}/routes", json=route_request)
    
    print(f"\n📥 Response Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Route created successfully!")
        print(f"Routes count: {len(result.get('routes', []))}")
        
        if result.get('routes'):
            route = result['routes'][0]
            print(f"\n📋 Route 0 details:")
            print(f"  - Total places: {len(route.get('places', []))}")
            
            if route.get('places'):
                print(f"\n  POIs in route:")
                for idx, place in enumerate(route['places']):
                    # Route builder uses 'place_id' and 'place_name' instead of 'id' and 'name'
                    place_id = place.get('place_id') or place.get('id')
                    place_name = place.get('place_name') or place.get('name')
                    print(f"    {idx+1}. {place_name} (ID: {place_id}, Category: {place.get('category', 'N/A')})")
                
                # 2. Test update POI
                print("\n" + "=" * 80)
                print("TEST 2: Update POI - Thay thế POI đầu tiên")
                print("=" * 80)
                
                first_poi = route['places'][0]
                first_poi_id = first_poi.get('place_id') or first_poi.get('id')
                first_poi_name = first_poi.get('place_name') or first_poi.get('name')
                first_poi_category = first_poi.get('category', 'Unknown')
                
                update_request = {
                    "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
                    "route_id": "route_0",
                    "poi_id_to_replace": first_poi_id,
                    "current_time": "2026-01-15T12:00:00"
                }
                
                print(f"\n📤 Sending update POI request...")
                print(f"  - Replacing POI: {first_poi_name} ({first_poi_id})")
                print(f"  - Category: {first_poi_category}")
                print(f"Request: {json.dumps(update_request, indent=2)}")
                
                update_response = requests.post(f"{BASE_URL}/update-poi", json=update_request)
                
                print(f"\n📥 Response Status: {update_response.status_code}")
                
                if update_response.status_code == 200:
                    update_result = update_response.json()
                    print(f"✅ POI updated successfully!")
                    print(f"\n📋 Update result:")
                    print(f"  - Old POI ID: {update_result.get('old_poi_id')}")
                    print(f"  - New POI: {update_result.get('new_poi', {}).get('name')} (ID: {update_result.get('new_poi', {}).get('id')})")
                    print(f"  - Category: {update_result.get('category')}")
                    print(f"\n  Updated POIs in route:")
                    for idx, poi in enumerate(update_result.get('updated_pois', [])):
                        print(f"    {idx+1}. POI ID: {poi.get('poi_id')}, Category: {poi.get('category')}")
                else:
                    print(f"❌ Update failed!")
                    print(f"Error: {update_response.text}")
        else:
            print("⚠️  No routes generated")
    else:
        print(f"❌ Route search failed!")
        print(f"Error: {response.text}")


def test_update_poi_error_cases():
    """Test các trường hợp lỗi"""
    
    print("\n" + "=" * 80)
    print("TEST 3: Error Cases")
    print("=" * 80)
    
    # Test 1: Invalid route_id
    print("\n📤 Test 3.1: Invalid route_id")
    invalid_route_request = {
        "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
        "route_id": "invalid_route_123",
        "poi_id_to_replace": "123e4567-e89b-12d3-a456-426614174000",
        "current_time": "2026-01-15T12:00:00"
    }
    
    response = requests.post(f"{BASE_URL}/update-poi", json=invalid_route_request)
    print(f"Response Status: {response.status_code}")
    print(f"Expected: 400 (Bad Request)")
    print(f"Error: {response.json().get('detail', 'N/A')}")
    
    # Test 2: Invalid POI ID
    print("\n📤 Test 3.2: Invalid POI ID")
    invalid_poi_request = {
        "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
        "route_id": "route_0",
        "poi_id_to_replace": "invalid-poi-id",
        "current_time": "2026-01-15T12:00:00"
    }
    
    response = requests.post(f"{BASE_URL}/update-poi", json=invalid_poi_request)
    print(f"Response Status: {response.status_code}")
    print(f"Expected: 400 (Bad Request)")
    print(f"Error: {response.json().get('detail', 'N/A')}")


if __name__ == "__main__":
    print("\n🚀 Starting Update POI API Tests\n")
    
    try:
        # Test 1 & 2: Route search và update
        test_route_search_and_update()
        
        # Test 3: Error cases
        test_update_poi_error_cases()
        
        print("\n" + "=" * 80)
        print("✅ All tests completed!")
        print("=" * 80)
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure the server is running on http://localhost:8000")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
