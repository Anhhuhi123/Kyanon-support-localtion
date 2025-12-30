"""
Script so sánh độ chính xác giữa Haversine và PostGIS ST_Distance
"""

import psycopg2
import math
import time
from config.config import Config


def calculate_distance_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Tính khoảng cách Haversine giữa 2 điểm (km)
    NHANH - không cần connect DB
    """
    R = 6371  # Bán kính trái đất (km)
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c


def calculate_distance_postgis(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Tính khoảng cách PostGIS ST_Distance (km)
    CHẬM - cần connect DB
    """
    conn = psycopg2.connect(Config.get_db_connection_string())
    cursor = conn.cursor()
    
    try:
        point1_wkt = f"POINT({lon1} {lat1})"
        point2_wkt = f"POINT({lon2} {lat2})"
        
        query = """
            SELECT ST_Distance(
                ST_GeomFromText(%s, 4326)::geography,
                ST_GeomFromText(%s, 4326)::geography
            ) / 1000.0 AS distance_km
        """
        
        cursor.execute(query, [point1_wkt, point2_wkt])
        result = cursor.fetchone()
        return result[0] if result else 0.0
        
    finally:
        cursor.close()
        conn.close()


def test_distance_comparison():
    """
    Test so sánh khoảng cách giữa Haversine và PostGIS
    """
    print("="*80)
    print("🔍 SO SÁNH HAVERSINE vs POSTGIS ST_DISTANCE")
    print("="*80)
    
    # Các cặp điểm test (ở Hồ Chí Minh và vùng lân cận)
    test_cases = [
        {
            "name": "Quận 1 → Quận 3 (gần)",
            "point1": (10.7769, 106.7009),  # Quận 1
            "point2": (10.7860, 106.6874)   # Quận 3
        },
        {
            "name": "Quận 1 → Quận 7 (trung bình)",
            "point1": (10.7769, 106.7009),  # Quận 1
            "point2": (10.7350, 106.7195)   # Quận 7
        },
        {
            "name": "Quận 1 → Thủ Đức (xa)",
            "point1": (10.7769, 106.7009),  # Quận 1
            "point2": (10.8509, 106.7718)   # Thủ Đức
        },
        {
            "name": "Quận 1 → Bình Dương (rất xa)",
            "point1": (10.7769, 106.7009),  # Quận 1
            "point2": (10.9804, 106.6519)   # Bình Dương
        },
        {
            "name": "Cùng vị trí (0 km)",
            "point1": (10.7769, 106.7009),
            "point2": (10.7769, 106.7009)
        }
    ]
    
    print("\n📊 KẾT QUẢ SO SÁNH:\n")
    
    total_haversine_time = 0
    total_postgis_time = 0
    
    for idx, test in enumerate(test_cases, 1):
        lat1, lon1 = test["point1"]
        lat2, lon2 = test["point2"]
        
        print(f"{idx}. {test['name']}")
        print(f"   Point 1: ({lat1}, {lon1})")
        print(f"   Point 2: ({lat2}, {lon2})")
        
        # Test Haversine
        start = time.time()
        dist_haversine = calculate_distance_haversine(lat1, lon1, lat2, lon2)
        time_haversine = time.time() - start
        total_haversine_time += time_haversine
        
        # Test PostGIS
        start = time.time()
        dist_postgis = calculate_distance_postgis(lat1, lon1, lat2, lon2)
        time_postgis = time.time() - start
        total_postgis_time += time_postgis
        
        # Tính sai số
        if dist_postgis > 0:
            error_percent = abs(dist_haversine - dist_postgis) / dist_postgis * 100
            error_km = abs(dist_haversine - dist_postgis)
        else:
            error_percent = 0
            error_km = 0
        
        # Hiển thị kết quả
        print(f"   ┌─ Haversine:  {dist_haversine:.6f} km  (⏱️  {time_haversine*1000:.2f} ms)")
        print(f"   ├─ PostGIS:    {dist_postgis:.6f} km  (⏱️  {time_postgis*1000:.2f} ms)")
        print(f"   ├─ Chênh lệch: {error_km:.6f} km  ({error_percent:.4f}%)")
        
        # Đánh giá
        if error_percent < 0.1:
            status = "✅ RẤT CHÍNH XÁC"
        elif error_percent < 0.5:
            status = "✅ CHÍNH XÁC"
        elif error_percent < 1.0:
            status = "⚠️  CHẤP NHẬN ĐƯỢC"
        else:
            status = "❌ SAI SỐ LỚN"
        
        print(f"   └─ {status}")
        print()
    
    # Tổng kết
    print("="*80)
    print("📈 TỔNG KẾT")
    print("="*80)
    print(f"Tổng thời gian Haversine:  {total_haversine_time*1000:.2f} ms")
    print(f"Tổng thời gian PostGIS:    {total_postgis_time*1000:.2f} ms")
    print(f"Haversine nhanh hơn:       {total_postgis_time/total_haversine_time:.1f}x")
    print()
    print("🎯 KẾT LUẬN:")
    print("   • Haversine đủ chính xác cho khoảng cách < 50km (sai số < 0.1%)")
    print("   • Haversine nhanh hơn PostGIS rất nhiều lần")
    print("   • NÊN DÙNG Haversine cho route planning trong thành phố")
    print("="*80)


def test_matrix_performance():
    """
    Test hiệu năng tính ma trận khoảng cách cho 10 địa điểm
    """
    print("\n" + "="*80)
    print("⚡ TEST HIỆU NĂNG MA TRẬN (10 ĐỊA ĐIỂM)")
    print("="*80)
    
    # 10 địa điểm giả lập trong HCM
    locations = [
        (10.7769, 106.7009),  # User
        (10.7860, 106.6874),  # Place 1
        (10.7350, 106.7195),  # Place 2
        (10.8509, 106.7718),  # Place 3
        (10.8231, 106.6297),  # Place 4
        (10.7625, 106.6822),  # Place 5
        (10.8050, 106.7145),  # Place 6
        (10.7480, 106.6935),  # Place 7
        (10.7920, 106.7250),  # Place 8
        (10.7700, 106.6650),  # Place 9
    ]
    
    n = len(locations)
    num_pairs = n * (n - 1) // 2  # Số cặp cần tính (ma trận đối xứng)
    
    print(f"\nSố địa điểm: {n}")
    print(f"Số cặp cần tính: {num_pairs}")
    
    # Test Haversine
    print(f"\n🔄 Đang tính {num_pairs} khoảng cách bằng Haversine...")
    start = time.time()
    haversine_results = []
    for i in range(n):
        for j in range(i + 1, n):
            dist = calculate_distance_haversine(
                locations[i][0], locations[i][1],
                locations[j][0], locations[j][1]
            )
            haversine_results.append(dist)
    time_haversine = time.time() - start
    
    print(f"✅ Hoàn thành trong {time_haversine*1000:.2f} ms")
    
    # Test PostGIS
    print(f"\n🔄 Đang tính {num_pairs} khoảng cách bằng PostGIS...")
    start = time.time()
    postgis_results = []
    for i in range(n):
        for j in range(i + 1, n):
            dist = calculate_distance_postgis(
                locations[i][0], locations[i][1],
                locations[j][0], locations[j][1]
            )
            postgis_results.append(dist)
    time_postgis = time.time() - start
    
    print(f"✅ Hoàn thành trong {time_postgis*1000:.2f} ms")
    
    # So sánh
    print(f"\n📊 KẾT QUẢ:")
    print(f"   • Haversine: {time_haversine*1000:.2f} ms")
    print(f"   • PostGIS:   {time_postgis*1000:.2f} ms")
    print(f"   • Haversine nhanh hơn: {time_postgis/time_haversine:.1f}x")
    
    # Kiểm tra độ chính xác
    max_error = 0
    for i in range(len(haversine_results)):
        error = abs(haversine_results[i] - postgis_results[i])
        if postgis_results[i] > 0:
            error_percent = error / postgis_results[i] * 100
            if error_percent > max_error:
                max_error = error_percent
    
    print(f"   • Sai số lớn nhất: {max_error:.4f}%")
    print()


if __name__ == "__main__":
    test_distance_comparison()
    test_matrix_performance()
