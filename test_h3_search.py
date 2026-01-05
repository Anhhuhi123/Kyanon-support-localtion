#!/usr/bin/env python3
"""
Test H3 + Redis Radius Search
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from Logic.h3_radius_search import H3RadiusSearch
from config.config import Config


def test_h3_search():
    """Test H3 + Redis search"""
    
    # Tọa độ test (HCM)
    latitude = 10.8294811
    longitude = 106.7737852
    transportation_mode = "BICYCLING"
    
    print("=" * 80)
    print("Testing H3 + Redis Radius Search")
    print("=" * 80)
    print(f"Location: ({latitude}, {longitude})")
    print(f"Mode: {transportation_mode}")
    print()
    
    # Khởi tạo searcher
    db_conn_str = Config.get_db_connection_string()
    searcher = H3RadiusSearch(db_conn_str)
    
    # Test lần 1 (cache miss)
    print("\n🔍 TEST 1: First search (cache miss expected)")
    print("-" * 80)
    results_1, radius_1 = searcher.search_locations(latitude, longitude, transportation_mode)
    print(f"\nResults: {len(results_1)} POIs")
    print(f"Radius: {radius_1}m")
    if results_1:
        print(f"\nSample (first 3):")
        for poi in results_1[:3]:
            print(f"  - {poi['name']}: {poi['distance_meters']}m, rating={poi['rating']}")
    
    # Test lần 2 (cache hit)
    print("\n\n🔍 TEST 2: Second search (cache hit expected)")
    print("-" * 80)
    results_2, radius_2 = searcher.search_locations(latitude, longitude, transportation_mode)
    print(f"\nResults: {len(results_2)} POIs")
    print(f"Radius: {radius_2}m")
    
    # So sánh
    print("\n\n📊 COMPARISON")
    print("-" * 80)
    print(f"Test 1: {len(results_1)} POIs")
    print(f"Test 2: {len(results_2)} POIs")
    print(f"Match: {len(results_1) == len(results_2)}")
    
    print("\n✅ Test completed!")


if __name__ == "__main__":
    test_h3_search()
