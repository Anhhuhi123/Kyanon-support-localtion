# API Endpoint Update: current_time Parameter

## Thay đổi

Đã thêm parameter `current_time` vào endpoint `/api/v1/semantic/routes` để hỗ trợ lọc POI theo thời gian mở cửa.

## Request Body

### Trước (vẫn hoạt động):
```json
{
  "latitude": 21.0285,
  "longitude": 105.8542,
  "transportation_mode": "WALKING",
  "semantic_query": "Food & Local Flavours,Culture & heritage",
  "max_time_minutes": 180,
  "target_places": 5,
  "max_routes": 3,
  "top_k_semantic": 10,
  "customer_like": false
}
```

### Sau (có thêm current_time):
```json
{
  "latitude": 21.0285,
  "longitude": 105.8542,
  "transportation_mode": "WALKING",
  "semantic_query": "Food & Local Flavours,Culture & heritage",
  "current_time": "2026-01-13T08:00:00",
  "max_time_minutes": 180,
  "target_places": 5,
  "max_routes": 3,
  "top_k_semantic": 10,
  "customer_like": false
}
```

## Parameter mới: `current_time`

- **Type**: `Optional[datetime]` (ISO 8601 format)
- **Required**: No (Optional)
- **Description**: Thời điểm hiện tại của user. Nếu None, không lọc theo thời gian mở cửa
- **Example**: `"2026-01-13T08:00:00"`
- **Format**: ISO 8601 datetime string

### Cách hoạt động:

1. **Nếu `current_time = null` hoặc không có**:
   - Không lọc theo thời gian
   - Trả về tất cả POI như bình thường
   - Backward compatible với API cũ

2. **Nếu có `current_time`**:
   - Tính time window: `[current_time, current_time + max_time_minutes]`
   - Lọc POI có overlap với time window
   - Validate opening hours trong routes
   - Trả về warnings nếu POI đóng cửa

## Response Format

### Khi có time filtering:

```json
{
  "status": "success",
  "query": "Food & Local Flavours,Culture & heritage",
  "spatial_info": {
    "transportation_mode": "WALKING",
    "radius_used": 1500,
    "total_spatial_locations": 45,
    "filtered_by_time": true,
    "time_window": {
      "start": "2026-01-13T08:00:00",
      "end": "2026-01-13T11:00:00"
    },
    "original_results_count": 100
  },
  "routes": [
    {
      "route_id": 1,
      "total_time_minutes": 150,
      "opening_hours_validated": true,
      "is_valid_timing": false,
      "timing_warnings": [
        "POI 'Restaurant ABC' is closed at Monday 07:30"
      ],
      "places": [...]
    }
  ]
}
```

### Fields mới trong response:

#### Trong `spatial_info`:
- `filtered_by_time` (boolean): True nếu đã lọc theo thời gian
- `time_window` (object): Time window đã dùng để lọc
  - `start` (string): Thời điểm bắt đầu
  - `end` (string): Thời điểm kết thúc
- `original_results_count` (int): Số POI trước khi lọc

#### Trong mỗi `route`:
- `opening_hours_validated` (boolean): True nếu đã validate opening hours
- `is_valid_timing` (boolean): True nếu tất cả POI mở cửa đúng giờ
- `timing_warnings` (array): Danh sách cảnh báo (nếu có POI đóng cửa)

## Ví dụ sử dụng

### Ví dụ 1: Không dùng time filtering
```bash
curl -X POST "http://localhost:8000/api/v1/semantic/routes" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 21.0285,
    "longitude": 105.8542,
    "transportation_mode": "WALKING",
    "semantic_query": "Food & Local Flavours",
    "max_time_minutes": 180
  }'
```

### Ví dụ 2: Dùng time filtering với current time
```bash
curl -X POST "http://localhost:8000/api/v1/semantic/routes" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 21.0285,
    "longitude": 105.8542,
    "transportation_mode": "WALKING",
    "semantic_query": "Food & Local Flavours",
    "current_time": "2026-01-13T08:00:00",
    "max_time_minutes": 180
  }'
```

### Ví dụ 3: Python requests
```python
import requests
from datetime import datetime

payload = {
    "latitude": 21.0285,
    "longitude": 105.8542,
    "transportation_mode": "WALKING",
    "semantic_query": "Food & Local Flavours",
    "current_time": datetime.now().isoformat(),  # Current time
    "max_time_minutes": 180,
    "target_places": 5,
    "max_routes": 3
}

response = requests.post(
    "http://localhost:8000/api/v1/semantic/routes",
    json=payload
)

data = response.json()

# Check if time filtering was applied
if data.get('spatial_info', {}).get('filtered_by_time'):
    print("Time filtering: ENABLED")
    print(f"POIs filtered: {data['spatial_info']['original_results_count']} -> {data['spatial_info']['total_spatial_locations']}")

# Check route timing validation
for route in data.get('routes', []):
    if not route.get('is_valid_timing', True):
        print(f"⚠️ Route {route['route_id']} has timing issues:")
        for warning in route.get('timing_warnings', []):
            print(f"  - {warning}")
```

## Test Script

Chạy test script để kiểm tra:

```bash
cd /Users/macbook/Desktop/Kyanon/Kyanon-support-localtion
source ../myenv/bin/activate
python scripts/test_connect/test_api_current_time.py
```

## Lưu ý

1. **Backward Compatible**: API vẫn hoạt động như cũ nếu không truyền `current_time`

2. **ISO 8601 Format**: `current_time` phải theo format ISO 8601:
   - `"2026-01-13T08:00:00"` ✅
   - `"2026-01-13 08:00:00"` ❌
   - `"13/01/2026 08:00"` ❌

3. **Timezone**: Hiện tại không xử lý timezone, giả định tất cả thời gian đều local

4. **Validation vs Filtering**:
   - **Filtering** (spatial search): Lọc POI có thể mở cửa trong time window
   - **Validation** (route): Kiểm tra POI có mở cửa tại thời điểm user đến chính xác

5. **POI không có open_hours**: Giả sử luôn mở cửa (không bị lọc)

## Files đã cập nhật

1. **`pydantics/semantic.py`**:
   - Thêm field `current_time: Optional[datetime]` vào `RouteSearchRequest`
   - Import `datetime` module

2. **`routers/v1/semantic_api.py`**:
   - Pass `current_datetime=request.current_time` xuống service layer

3. **`scripts/test_connect/test_api_current_time.py`** (MỚI):
   - Test script demo API với current_time parameter

## Swagger UI

Sau khi start server, truy cập http://localhost:8000/docs để thấy API documentation với parameter mới.

Field `current_time` sẽ xuất hiện trong request body schema với:
- Type: `string (date-time)`
- Format: `date-time`
- Example: `"2026-01-13T08:00:00"`
- Required: `false`
