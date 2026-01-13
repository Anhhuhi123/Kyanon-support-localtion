# Time-Based POI Filtering Documentation

## Tổng quan

Hệ thống đã được cập nhật để hỗ trợ lọc POI (Points of Interest) dựa trên thời gian mở cửa của từng địa điểm. Tính năng này giúp đảm bảo rằng các địa điểm được đề xuất trong lộ trình sẽ mở cửa khi user đến.

## Các thay đổi chính

### 1. Module mới: `utils/time_utils.py`

Module này cung cấp các utility functions để xử lý logic thời gian mở cửa:

#### Các hàm chính:

- **`is_open_at_time(open_hours, check_datetime)`**: Kiểm tra POI có mở cửa tại thời điểm cụ thể
- **`overlaps_with_time_window(open_hours, start_datetime, end_datetime)`**: Kiểm tra POI có overlap với time window
- **`filter_open_pois(pois, start_datetime, end_datetime)`**: Lọc danh sách POI theo time window
- **`validate_route_timing(route, start_datetime, ...)`**: Validate toàn bộ route xem POI có mở cửa khi user đến không

### 2. Cập nhật `h3_radius_search.py`

- Thêm field `open_hours` vào query PostgreSQL
- Data format: 
```python
[
    {'day': 'Monday', 'hours': [{'start': '08:00', 'end': '22:00'}]},
    {'day': 'Tuesday', 'hours': [{'start': '08:00', 'end': '22:00'}]},
    ...
]
```

### 3. Cập nhật `location_service.py`

**Hàm `find_nearest_locations` có thêm 2 tham số:**

- `current_datetime` (Optional[datetime]): Thời điểm hiện tại của user
- `max_time_minutes` (Optional[int]): Thời gian tối đa user có

**Logic:**
1. Spatial search lấy TẤT CẢ POI trong bán kính
2. Nếu có `current_datetime` và `max_time_minutes`:
   - Tính time window: `[current_datetime, current_datetime + max_time_minutes]`
   - Lọc chỉ giữ các POI có overlap với time window này
3. Trả về kết quả đã lọc

### 4. Cập nhật `route.py`

**Hàm `build_routes` có thêm tham số:**

- `current_datetime` (Optional[datetime]): Thời điểm bắt đầu route

**Logic validation:**
- Sau khi xây dựng route, validate từng POI trong route
- Tính thời gian đến từng POI dựa trên:
  - Travel time từ POI trước
  - Stay time (30 phút mặc định)
- Kiểm tra POI có mở cửa tại thời điểm đến không
- Trả về warnings nếu có POI đóng cửa

### 5. Cập nhật `semantic_search_service.py`

**Hàm `search_combined_with_routes` có thêm tham số:**

- `current_datetime` (Optional[datetime]): Thời điểm hiện tại

**Workflow mới:**
1. **Spatial Search với time filtering:**
   - Lấy TẤT CẢ POI trong bán kính
   - Lọc các POI có overlap với time window `[current_datetime, current_datetime + max_time_minutes]`

2. **Semantic Search:**
   - Tìm kiếm semantic trong danh sách đã lọc

3. **Route Building với validation:**
   - Xây dựng routes
   - Validate opening hours cho từng POI trong route
   - Báo warning nếu có POI đóng cửa

## Cách sử dụng

### Ví dụ 1: Tìm POI có mở cửa trong 3 giờ tới

```python
from datetime import datetime
from services.location_service import LocationService

location_service = LocationService(db_connection_string)

# User ở Hà Nội lúc 7:00 sáng, có 3 giờ (180 phút)
current_time = datetime(2026, 1, 13, 7, 0)  # Monday 07:00
max_time = 180  # 180 minutes = 3 hours

results = location_service.find_nearest_locations(
    latitude=21.0285,
    longitude=105.8542,
    transportation_mode="WALKING",
    current_datetime=current_time,
    max_time_minutes=max_time
)

# results sẽ chỉ chứa POI có overlap với time window [07:00, 10:00]
print(f"Found {results['total_results']} POIs open during 07:00-10:00")
```

### Ví dụ 2: Xây dựng route với validation thời gian

```python
from datetime import datetime
from services.semantic_search_service import SemanticSearchService

semantic_service = SemanticSearchService()

# User bắt đầu route lúc 8:00 sáng
current_time = datetime(2026, 1, 13, 8, 0)  # Monday 08:00

results = semantic_service.search_combined_with_routes(
    latitude=21.0285,
    longitude=105.8542,
    transportation_mode="WALKING",
    semantic_query="Food & Local Flavours,Culture & heritage",
    max_time_minutes=180,
    target_places=5,
    max_routes=3,
    current_datetime=current_time  # Thêm tham số này
)

# Kiểm tra routes có valid về timing không
for route in results['routes']:
    print(f"Route {route['route_id']}:")
    if route.get('opening_hours_validated'):
        if route.get('is_valid_timing'):
            print("  ✅ All POIs are open when you arrive")
        else:
            print("  ⚠️ Some POIs may be closed:")
            for warning in route.get('timing_warnings', []):
                print(f"    - {warning}")
```

### Ví dụ 3: Kiểm tra POI có mở cửa không

```python
from datetime import datetime
from utils.time_utils import TimeUtils

poi_open_hours = [
    {'day': 'Monday', 'hours': [{'start': '08:00', 'end': '22:00'}]},
    {'day': 'Tuesday', 'hours': [{'start': '08:00', 'end': '22:00'}]},
    # ...
]

# Kiểm tra lúc 10:00 sáng thứ 2
check_time = datetime(2026, 1, 13, 10, 0)  # Monday 10:00
is_open = TimeUtils.is_open_at_time(poi_open_hours, check_time)

print(f"POI is {'OPEN' if is_open else 'CLOSED'} at {check_time.strftime('%A %H:%M')}")
```

## Format dữ liệu Opening Hours

```python
open_hours = [
    {
        'day': 'Monday',  # Tên ngày tiếng Anh
        'hours': [
            {'start': '08:00', 'end': '12:00'},  # Có thể có nhiều khoảng thời gian
            {'start': '13:00', 'end': '22:00'}
        ]
    },
    {
        'day': 'Tuesday',
        'hours': []  # Rỗng = đóng cửa cả ngày
    },
    {
        'day': 'Wednesday',
        'hours': [{'start': '00:00', 'end': '23:59'}]  # Mở cửa cả ngày
    },
    # ... các ngày khác
]
```

## Response Format

### Location Service Response

```json
{
    "status": "success",
    "transportation_mode": "WALKING",
    "center": {"latitude": 21.0285, "longitude": 105.8542},
    "radius_used": 1500,
    "total_results": 45,
    "filtered_by_time": true,
    "time_window": {
        "start": "2026-01-13T07:00:00",
        "end": "2026-01-13T10:00:00"
    },
    "original_results_count": 100,
    "results": [
        {
            "id": "uuid-123",
            "name": "Restaurant ABC",
            "poi_type": "restaurant",
            "lat": 21.0290,
            "lon": 105.8550,
            "distance_meters": 120.5,
            "open_hours": [...]
        }
    ]
}
```

### Route Response with Timing Validation

```json
{
    "status": "success",
    "routes": [
        {
            "route_id": 1,
            "total_time_minutes": 150,
            "opening_hours_validated": true,
            "is_valid_timing": false,
            "timing_warnings": [
                "POI 'Museum XYZ' is closed at Monday 08:30"
            ],
            "places": [
                {
                    "id": "uuid-123",
                    "name": "Restaurant ABC",
                    "order": 1,
                    "open_hours": [...]
                }
            ]
        }
    ]
}
```

## Lưu ý quan trọng

1. **Backward Compatibility**: Các hàm vẫn hoạt động bình thường nếu không truyền `current_datetime`. Trong trường hợp này, không có time filtering.

2. **Performance**: Time filtering được thực hiện sau spatial search để tối ưu performance. Chỉ lọc trên kết quả đã có từ H3 + Redis cache.

3. **Validation vs Filtering**:
   - **Filtering** (spatial search): Lọc POI có overlap với time window
   - **Validation** (route building): Kiểm tra POI có mở cửa khi user đến chính xác thời điểm đó

4. **Edge cases**:
   - POI không có `open_hours` → Giả sử luôn mở cửa (return True)
   - Time window qua đêm (overnight) → Xử lý đúng với logic cross-day
   - Multiple hours trong 1 ngày → Hỗ trợ (VD: 8:00-12:00, 13:00-22:00)

## Testing

Chạy test script để kiểm tra:

```bash
cd /Users/macbook/Desktop/Kyanon/Kyanon-support-localtion
source ../myenv/bin/activate
python scripts/test_connect/test_time_filtering.py
```

Test coverage:
- ✅ Kiểm tra POI mở cửa tại thời điểm cụ thể
- ✅ Kiểm tra overlap với time window
- ✅ Lọc danh sách POI
- ✅ Tính toán thời gian đến
- ✅ Validate route timing

## Migration Notes

Để sử dụng tính năng mới:

1. Đảm bảo field `open_hours` đã có trong database table `PoiClean`
2. Update existing code để truyền `current_datetime` nếu muốn enable time filtering
3. Check response có `opening_hours_validated` và `timing_warnings` để hiển thị cho user

## Future Enhancements

Có thể mở rộng thêm:
- Tự động điều chỉnh route nếu POI đóng cửa
- Suggest thời gian tốt nhất để bắt đầu route
- Cache opening hours để tối ưu performance
- Hỗ trợ special hours (holidays, events)
