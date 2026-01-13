# Tóm tắt Tính năng Lọc POI theo Thời gian Mở cửa

## Tổng quan thay đổi

Đã implement tính năng lọc POI dựa trên thời gian mở cửa (`open_hours`) để đảm bảo các địa điểm trong route sẽ mở cửa khi user đến.

## Luồng xử lý

### 1. Spatial Search (Bước 1)
**File: `location_service.py`**

- **Input mới**: 
  - `current_datetime`: Thời điểm hiện tại của user (ví dụ: 2026-01-13 07:00)
  - `max_time_minutes`: Thời gian tối đa user có (ví dụ: 180 phút = 3 giờ)

- **Logic**:
  1. Tìm TẤT CẢ POI trong bán kính (H3 + Redis)
  2. **Nếu có `current_datetime` và `max_time_minutes`**:
     - Tính time window: `[07:00, 10:00]` (current + max_time)
     - Lọc chỉ giữ POI có overlap với time window này
     - Ví dụ: POI mở cửa 08:00-22:00 → **GIỮ LẠI** (overlap với 07:00-10:00)
     - Ví dụ: POI mở cửa 11:00-20:00 → **LỌC BỎ** (không overlap)

- **Output**: Danh sách POI đã lọc theo thời gian

### 2. Semantic Search (Bước 2)
**File: `semantic_search_service.py`**

- Tìm kiếm semantic trong danh sách POI đã lọc từ bước 1
- Không thay đổi logic, chỉ nhận input đã được lọc

### 3. Route Building + Validation (Bước 3)
**File: `route.py`**

- **Input mới**: `current_datetime`

- **Logic validation**:
  1. Xây dựng routes như bình thường
  2. **Sau khi có routes, validate từng POI**:
     - Tính thời gian đến POI: `arrival_time = current_time + travel_time`
     - Kiểm tra POI có mở cửa tại `arrival_time` không
     - Nếu đóng cửa → Thêm vào `timing_warnings`

- **Output**: 
  - Routes với thông tin validation
  - `is_valid_timing`: True/False
  - `timing_warnings`: Danh sách cảnh báo (nếu có)

## Ví dụ cụ thể

### Scenario: User ở Hà Nội lúc 7:00 sáng, có 3 giờ

```python
current_datetime = datetime(2026, 1, 13, 7, 0)  # Monday 07:00
max_time_minutes = 180  # 3 hours
```

**Time window**: 07:00 - 10:00

### POI Examples:

| POI | Opening Hours | Overlap? | Kết quả |
|-----|---------------|----------|---------|
| Restaurant A | Monday 08:00-22:00 | ✅ Có (08:00-10:00) | **Giữ lại** |
| Museum B | Monday 11:00-17:00 | ❌ Không | **Lọc bỏ** |
| Cafe C | Monday 06:00-12:00 | ✅ Có (07:00-10:00) | **Giữ lại** |
| Store D | 24/7 | ✅ Có (luôn mở) | **Giữ lại** |

### Route Validation Example:

Giả sử route: User → Restaurant A (30 phút) → Cafe C (40 phút)

1. **Restaurant A**:
   - Departure: 07:00
   - Travel: 30 phút
   - Arrival: 07:30
   - Opening hours: 08:00-22:00
   - **Result**: ❌ CLOSED → Warning: "Restaurant A is closed at Monday 07:30"

2. **Cafe C**:
   - Departure: 08:00 (07:30 + 30 phút stay)
   - Travel: 40 phút
   - Arrival: 08:40
   - Opening hours: 06:00-12:00
   - **Result**: ✅ OPEN

## Files đã thay đổi

### 1. **utils/time_utils.py** (MỚI)
Module xử lý logic thời gian:
- `is_open_at_time()`: Kiểm tra POI mở cửa tại thời điểm cụ thể
- `overlaps_with_time_window()`: Kiểm tra overlap với time window
- `filter_open_pois()`: Lọc danh sách POI
- `validate_route_timing()`: Validate route

### 2. **h3_radius_search.py**
- Thêm `open_hours` vào SQL query
- Parse `open_hours` từ database

### 3. **location_service.py**
- Thêm params: `current_datetime`, `max_time_minutes`
- Gọi `TimeUtils.filter_open_pois()` để lọc kết quả

### 4. **route.py**
- Thêm param: `current_datetime`
- Gọi `TimeUtils.validate_route_timing()` sau khi build route
- Thêm `timing_warnings` vào response

### 5. **semantic_search_service.py**
- Pass `current_datetime` và `max_time_minutes` xuống các hàm con
- Propagate params qua các layers

## Cách sử dụng

### Option 1: Không dùng time filtering (backward compatible)
```python
# Gọi như cũ, không truyền current_datetime
results = semantic_service.search_combined_with_routes(
    latitude=21.0285,
    longitude=105.8542,
    transportation_mode="WALKING",
    semantic_query="Food & Local Flavours",
    max_time_minutes=180
)
# → Không lọc theo thời gian
```

### Option 2: Dùng time filtering
```python
from datetime import datetime

current_time = datetime.now()  # Hoặc datetime(2026, 1, 13, 7, 0)

results = semantic_service.search_combined_with_routes(
    latitude=21.0285,
    longitude=105.8542,
    transportation_mode="WALKING",
    semantic_query="Food & Local Flavours",
    max_time_minutes=180,
    current_datetime=current_time  # Thêm tham số này
)
# → Lọc POI theo thời gian và validate routes
```

### Xử lý response
```python
for route in results['routes']:
    if not route.get('is_valid_timing', True):
        print(f"⚠️ Route {route['route_id']} có vấn đề:")
        for warning in route.get('timing_warnings', []):
            print(f"   - {warning}")
```

## Format dữ liệu open_hours

```python
open_hours = [
    {'day': 'Monday', 'hours': [{'start': '08:00', 'end': '22:00'}]},
    {'day': 'Tuesday', 'hours': []},  # Đóng cửa
    {'day': 'Wednesday', 'hours': [
        {'start': '08:00', 'end': '12:00'},
        {'start': '13:00', 'end': '22:00'}  # Multiple hours
    ]},
    # ... các ngày khác
]
```

## Testing

```bash
cd /Users/macbook/Desktop/Kyanon/Kyanon-support-localtion
source ../myenv/bin/activate
python scripts/test_connect/test_time_filtering.py
```

Test đã pass ✅:
- Kiểm tra POI mở cửa tại thời điểm cụ thể
- Kiểm tra overlap với time window
- Lọc danh sách POI
- Validate route timing

## Lợi ích

1. **User Experience tốt hơn**: Không recommend POI đóng cửa
2. **Tính năng thông minh**: Tự động lọc và validate
3. **Flexibility**: Có thể bật/tắt tính năng bằng cách truyền/không truyền `current_datetime`
4. **Performance**: Lọc hiệu quả với time complexity O(n) sau spatial search

## Lưu ý

- POI không có `open_hours` → Giả sử luôn mở (không lọc)
- Time window có thể qua đêm (VD: 23:00 - 02:00) → Logic xử lý đúng
- Validation chỉ cảnh báo, không tự động loại bỏ POI khỏi route

## Documentation

Chi tiết đầy đủ xem tại: [TIME_FILTERING.md](./TIME_FILTERING.md)
