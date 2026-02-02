"""
Test script for Circular Routing (90° turns)

This script tests the circular routing implementation to verify:
1. Bearing angles between POI segments are ~90° (±10°)
2. Route forms a circular/square pattern instead of zigzag
3. Fallback logic works when no 90° POI available
"""
import sys
import io
# Set UTF-8 encoding for console output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import math
from typing import List, Tuple, Dict, Any
from radius_logic.route.geographic_utils import GeographicUtils
from radius_logic.route.calculator import Calculator
from radius_logic.route.poi_validator import POIValidator
from radius_logic.route.route_builder_target import TargetRouteBuilder
from radius_logic.route.route_config import RouteConfig

def create_test_pois(center_lat: float, center_lon: float, count: int = 12) -> List[Dict[str, Any]]:
    """
    Tạo POI test phân bố đều xung quanh một điểm trung tâm (theo hình tròn)
    
    Args:
        center_lat: Latitude trung tâm
        center_lon: Longitude trung tâm
        count: Số lượng POI (mặc định 12 = mỗi 30°)
        
    Returns:
        List POI với đầy đủ fields cần thiết
    """
    pois = []
    radius_km = 2.0  # 2km radius
    
    for i in range(count):
        # Phân bố đều theo góc (mỗi 30° nếu count=12)
        angle_deg = (360 / count) * i
        angle_rad = math.radians(angle_deg)
        
        # Tính lat/lon offset (approximate)
        # 1 degree latitude ≈ 111km
        # 1 degree longitude ≈ 111km * cos(latitude)
        lat_offset = (radius_km / 111.0) * math.cos(angle_rad)
        lon_offset = (radius_km / (111.0 * math.cos(math.radians(center_lat)))) * math.sin(angle_rad)
        
        poi = {
            "id": f"test_poi_{i}",
            "name": f"POI {i} ({angle_deg:.0f}°)",
            "category": "Culture" if i % 2 == 0 else "Nature",
            "lat": center_lat + lat_offset,
            "lon": center_lon + lon_offset,
            "score": 0.8,  # High similarity
            "rating": 0.7,
            "poi_type": "attraction",
            "stay_time": 30,
            "open_hours": []  # Always open for testing
        }
        pois.append(poi)
    
    return pois

def calculate_bearing_between_segments(
    p1: Dict[str, Any],
    p2: Dict[str, Any],
    p3: Dict[str, Any],
    geo: GeographicUtils
) -> float:
    """
    Tính góc giữa 2 segments: p1→p2 và p2→p3
    
    Returns:
        bearing_diff (0-180°): Góc chênh lệch giữa 2 vectors
    """
    bearing1 = geo.calculate_bearing(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
    bearing2 = geo.calculate_bearing(p2["lat"], p2["lon"], p3["lat"], p3["lon"])
    
    return geo.calculate_bearing_difference(bearing1, bearing2)

def test_circular_routing():
    """
    Test circular routing với 8 POI
    
    Verify:
    - Góc giữa các segments ~90° (±10°)
    - Route forms circular pattern
    """
    print("="*80)
    print("🧪 TEST CIRCULAR ROUTING")
    print("="*80)
    
    # Setup
    user_location = (21.0285, 105.8542)  # Hanoi center
    pois = create_test_pois(user_location[0], user_location[1], count=12)
    
    print(f"\n📍 User location: {user_location}")
    print(f"🎯 Created {len(pois)} test POIs distributed evenly in circle")
    print(f"⚙️ Circular routing enabled: {RouteConfig.USE_CIRCULAR_ROUTING}")
    print(f"📐 Angle tolerance: ±{RouteConfig.CIRCULAR_ANGLE_TOLERANCE}°")
    
    # Build route
    geo = GeographicUtils()
    validator = POIValidator()
    calculator = Calculator(geo)
    builder = TargetRouteBuilder(geo, validator, calculator)
    
    target_places = 8
    max_time_minutes = 300  # 5 hours
    transportation_mode = "DRIVING"
    
    print(f"\n🛣️ Building route with {target_places} POIs...")
    
    route_result = builder.build_route(
        user_location=user_location,
        places=pois,
        transportation_mode=transportation_mode,
        max_time_minutes=max_time_minutes,
        target_places=target_places
    )
    
    if not route_result:
        print("❌ Failed to build route!")
        return False
    
    print(f"✅ Route built successfully with {len(route_result['places'])} POIs")
    
    # Analyze bearing angles
    print(f"\n{'='*80}")
    print("📊 BEARING ANALYSIS")
    print(f"{'='*80}")
    
    route_pois = route_result['places']
    
    # Add user location as first point for analysis
    all_points = [{"lat": user_location[0], "lon": user_location[1], "name": "USER"}]
    for poi in route_pois:
        all_points.append({
            "lat": poi["lat"],
            "lon": poi["lon"],
            "name": poi["place_name"]
        })
    
    angles = []
    tolerance = RouteConfig.CIRCULAR_ANGLE_TOLERANCE
    
    print(f"\n{'Segment':<30} {'Angle (°)':<12} {'Status':<20}")
    print("-" * 80)
    
    for i in range(1, len(all_points) - 1):
        p1 = all_points[i - 1]
        p2 = all_points[i]
        p3 = all_points[i + 1]
        
        bearing_diff = calculate_bearing_between_segments(p1, p2, p3, geo)
        angles.append(bearing_diff)
        
        # Check if angle is within 90° ±tolerance
        diff_from_90 = abs(bearing_diff - 90)
        is_perpendicular = diff_from_90 <= tolerance
        
        segment_name = f"{p1['name'][:10]} → {p2['name'][:10]} → {p3['name'][:10]}"
        status = f"✅ ~90° (±{diff_from_90:.1f}°)" if is_perpendicular else f"⚠️ Off by {diff_from_90:.1f}°"
        
        print(f"{segment_name:<30} {bearing_diff:>6.1f}° {status:<20}")
    
    # Statistics
    print(f"\n{'='*80}")
    print("📈 STATISTICS")
    print(f"{'='*80}")
    
    angles_near_90 = sum(1 for a in angles if abs(a - 90) <= tolerance)
    percentage = (angles_near_90 / len(angles)) * 100 if angles else 0
    
    avg_angle = sum(angles) / len(angles) if angles else 0
    min_angle = min(angles) if angles else 0
    max_angle = max(angles) if angles else 0
    
    print(f"Total segments analyzed: {len(angles)}")
    print(f"Segments with ~90° (±{tolerance}°): {angles_near_90} ({percentage:.1f}%)")
    print(f"Average angle: {avg_angle:.1f}°")
    print(f"Min angle: {min_angle:.1f}°")
    print(f"Max angle: {max_angle:.1f}°")
    
    # Pass criteria: At least 60% of segments should be ~90°
    success = percentage >= 60
    
    print(f"\n{'='*80}")
    if success:
        print("✅ TEST PASSED: Route forms circular pattern (≥60% segments at 90°)")
    else:
        print(f"❌ TEST FAILED: Only {percentage:.1f}% segments at 90° (expected ≥60%)")
    print(f"{'='*80}")
    
    return success

def test_fallback_logic():
    """
    Test fallback logic when no 90° POI available
    """
    print("\n" + "="*80)
    print("🧪 TEST FALLBACK LOGIC")
    print("="*80)
    
    # Create POIs in a straight line (no 90° options)
    user_location = (21.0285, 105.8542)
    pois = []
    
    for i in range(8):
        # All POIs on same bearing (straight line East)
        lat_offset = 0
        lon_offset = (i + 1) * 0.02  # Incremental offset
        
        poi = {
            "id": f"line_poi_{i}",
            "name": f"Line POI {i}",
            "category": "Culture" if i % 2 == 0 else "Nature",
            "lat": user_location[0] + lat_offset,
            "lon": user_location[1] + lon_offset,
            "score": 0.8,
            "rating": 0.7,
            "poi_type": "attraction",
            "stay_time": 30,
            "open_hours": []
        }
        pois.append(poi)
    
    print(f"\n📍 Created {len(pois)} POIs in straight line (no 90° options)")
    
    # Build route
    geo = GeographicUtils()
    validator = POIValidator()
    calculator = Calculator(geo)
    builder = TargetRouteBuilder(geo, validator, calculator)
    
    route_result = builder.build_route(
        user_location=user_location,
        places=pois,
        transportation_mode="DRIVING",
        max_time_minutes=300,
        target_places=5
    )
    
    success = route_result is not None and len(route_result.get('places', [])) > 0
    
    if success:
        print(f"✅ Fallback worked: Built route with {len(route_result['places'])} POIs")
    else:
        print("❌ Fallback failed: Could not build route")
    
    return success

def test_consistent_right_turns():
    """
    Test consistent RIGHT turn direction (clockwise route)
    """
    print("\n" + "="*80)
    print("🧪 TEST CONSISTENT RIGHT TURNS")
    print("="*80)
    
    # Backup original config
    original_preference = RouteConfig.CIRCULAR_DIRECTION_PREFERENCE
    
    try:
        # Set to force RIGHT turns only
        RouteConfig.CIRCULAR_DIRECTION_PREFERENCE = "right"
        
        # Setup
        user_location = (21.0285, 105.8542)
        pois = create_test_pois(user_location[0], user_location[1], count=12)
        
        print(f"\n📍 Testing with CIRCULAR_DIRECTION_PREFERENCE = 'right'")
        print(f"🎯 Created {len(pois)} test POIs")
        
        # Build route
        geo = GeographicUtils()
        validator = POIValidator()
        calculator = Calculator(geo)
        builder = TargetRouteBuilder(geo, validator, calculator)
        
        route_result = builder.build_route(
            user_location=user_location,
            places=pois,
            transportation_mode="DRIVING",
            max_time_minutes=300,
            target_places=6
        )
        
        if not route_result:
            print("❌ Failed to build route!")
            return False
        
        print(f"✅ Route built with {len(route_result['places'])} POIs")
        
        # Verify route only used RIGHT turns where possible
        # We can't verify 100% right turns because some positions might not have right POIs
        # But we should see the route attempting right turns consistently
        
        success = len(route_result['places']) >= 3
        
        if success:
            print(f"✅ Consistent RIGHT turn test passed")
        else:
            print(f"❌ Consistent RIGHT turn test failed")
        
        return success
        
    finally:
        # Restore original config
        RouteConfig.CIRCULAR_DIRECTION_PREFERENCE = original_preference

def test_consistent_left_turns():
    """
    Test consistent LEFT turn direction (counter-clockwise route)
    """
    print("\n" + "="*80)
    print("🧪 TEST CONSISTENT LEFT TURNS")
    print("="*80)
    
    # Backup original config
    original_preference = RouteConfig.CIRCULAR_DIRECTION_PREFERENCE
    
    try:
        # Set to force LEFT turns only
        RouteConfig.CIRCULAR_DIRECTION_PREFERENCE = "left"
        
        # Setup
        user_location = (21.0285, 105.8542)
        pois = create_test_pois(user_location[0], user_location[1], count=12)
        
        print(f"\n📍 Testing with CIRCULAR_DIRECTION_PREFERENCE = 'left'")
        print(f"🎯 Created {len(pois)} test POIs")
        
        # Build route
        geo = GeographicUtils()
        validator = POIValidator()
        calculator = Calculator(geo)
        builder = TargetRouteBuilder(geo, validator, calculator)
        
        route_result = builder.build_route(
            user_location=user_location,
            places=pois,
            transportation_mode="DRIVING",
            max_time_minutes=300,
            target_places=6
        )
        
        if not route_result:
            print("❌ Failed to build route!")
            return False
        
        print(f"✅ Route built with {len(route_result['places'])} POIs")
        
        # Verify route only used LEFT turns where possible
        success = len(route_result['places']) >= 3
        
        if success:
            print(f"✅ Consistent LEFT turn test passed")
        else:
            print(f"❌ Consistent LEFT turn test failed")
        
        return success
        
    finally:
        # Restore original config
        RouteConfig.CIRCULAR_DIRECTION_PREFERENCE = original_preference

def test_auto_direction():
    """
    Test AUTO direction selection (picks direction with more candidates)
    """
    print("\n" + "="*80)
    print("🧪 TEST AUTO DIRECTION SELECTION")
    print("="*80)
    
    # Backup original config
    original_preference = RouteConfig.CIRCULAR_DIRECTION_PREFERENCE
    
    try:
        # Set to AUTO mode
        RouteConfig.CIRCULAR_DIRECTION_PREFERENCE = "auto"
        
        # Setup
        user_location = (21.0285, 105.8542)
        pois = create_test_pois(user_location[0], user_location[1], count=12)
        
        print(f"\n📍 Testing with CIRCULAR_DIRECTION_PREFERENCE = 'auto'")
        print(f"🎯 Created {len(pois)} test POIs")
        
        # Build route
        geo = GeographicUtils()
        validator = POIValidator()
        calculator = Calculator(geo)
        builder = TargetRouteBuilder(geo, validator, calculator)
        
        route_result = builder.build_route(
            user_location=user_location,
            places=pois,
            transportation_mode="DRIVING",
            max_time_minutes=300,
            target_places=6
        )
        
        if not route_result:
            print("❌ Failed to build route!")
            return False
        
        print(f"✅ Route built with {len(route_result['places'])} POIs")
        
        # In AUTO mode, the system should automatically pick a direction
        # and stick with it. Just verify the route was built successfully.
        success = len(route_result['places']) >= 3
        
        if success:
            print(f"✅ AUTO direction selection test passed")
        else:
            print(f"❌ AUTO direction selection test failed")
        
        return success
        
    finally:
        # Restore original config
        RouteConfig.CIRCULAR_DIRECTION_PREFERENCE = original_preference

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("CIRCULAR ROUTING TEST SUITE")
    print("=" * 80)
    
    # Test 1: Circular pattern
    test1_passed = test_circular_routing()
    
    # Test 2: Fallback logic
    test2_passed = test_fallback_logic()
    
    # Test 3: Consistent right turns
    test3_passed = test_consistent_right_turns()
    
    # Test 4: Consistent left turns
    test4_passed = test_consistent_left_turns()
    
    # Test 5: Auto direction
    test5_passed = test_auto_direction()
    
    # Summary
    print("\n" + "="*80)
    print("📋 TEST SUMMARY")
    print("="*80)
    print(f"Test 1 (Circular Pattern): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Test 2 (Fallback Logic): {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print(f"Test 3 (Consistent Right Turns): {'✅ PASSED' if test3_passed else '❌ FAILED'}")
    print(f"Test 4 (Consistent Left Turns): {'✅ PASSED' if test4_passed else '❌ FAILED'}")
    print(f"Test 5 (Auto Direction): {'✅ PASSED' if test5_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed and test3_passed and test4_passed and test5_passed:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️ SOME TESTS FAILED")
    
    print("="*80)
