# Response Format Update: Opening Hours in Route Results

## Thay đổi

Khi truyền `current_time` vào API endpoint `/api/v1/semantic/routes`, mỗi POI trong route sẽ có thêm thông tin:
- `arrival_time`: Thời điểm user đến POI đó
- `opening_hours_today`: Thông tin mở cửa cụ thể cho ngày đó

## Response Format Mới

### Cấu trúc mỗi Place trong Route:

```json
{
  "place_id": "df7b73df-00ee-4bd1-bab4-a8f46bb99b8f",
  "place_name": "BÚP Sky Cuisine",
  "poi_type": "Restaurant,Cocktail bar,Fast food restaurant,Lounge",
  "address": "65-67-69 Nguyễn Thái Bình, Phường Nguyễn Thái Bình, Quận 1",
  "lat": 10.7694071,
  "lon": 106.7001448,
  "similarity": 0.835,
  "rating": 0.783,
  "combined_score": 0.814,
  "travel_time_minutes": 7.7,
  "stay_time_minutes": 30,
  "route_id": 1,
  "order": 1,
  
  // ===== CÁC FIELDS MỚI =====
  "arrival_time": "2026-01-13 08:07:42",
  "opening_hours_today": {
    "day": "Monday",
    "date": "2026-01-13",
    "is_open": true,
    "hours": [
      {
        "start": "08:00",
        "end": "22:00"
      }
    ]
  }
}
```

## Chi tiết các fields mới

### 1. `arrival_time` (string)

**Mô tả**: Thời điểm user đến POI này (tính toán dựa trên current_time + travel_time + stay_time của các POI trước)

**Format**: `"YYYY-MM-DD HH:MM:SS"`

**Ví dụ**:
- POI đầu tiên (order=1): `"2026-01-13 08:07:42"` (current_time + travel_time từ user)
- POI thứ 2 (order=2): `"2026-01-13 08:45:12"` (arrival_time POI 1 + stay_time POI 1 + travel_time)

### 2. `opening_hours_today` (object)

**Mô tả**: Thông tin mở cửa của POI cho ngày cụ thể (ngày user đến)

**Structure**:
```json
{
  "day": "Monday",           // Tên ngày trong tuần
  "date": "2026-01-13",      // Ngày cụ thể (YYYY-MM-DD)
  "is_open": true,           // POI có mở cửa trong ngày này không
  "hours": [                 // Danh sách khung giờ mở cửa
    {
      "start": "08:00",      // Giờ mở cửa (HH:MM)
      "end": "22:00"         // Giờ đóng cửa (HH:MM)
    }
  ]
}
```

**Các trường hợp đặc biệt**:

#### Case 1: POI mở cửa bình thường
```json
{
  "day": "Monday",
  "date": "2026-01-13",
  "is_open": true,
  "hours": [
    {"start": "08:00", "end": "22:00"}
  ]
}
```

#### Case 2: POI có nhiều khung giờ (mở cửa 2 ca)
```json
{
  "day": "Monday",
  "date": "2026-01-13",
  "is_open": true,
  "hours": [
    {"start": "08:00", "end": "12:00"},
    {"start": "13:00", "end": "22:00"}
  ]
}
```

#### Case 3: POI mở cửa 24/7
```json
{
  "day": "Monday",
  "date": "2026-01-13",
  "is_open": true,
  "hours": [
    {"start": "00:00", "end": "23:59"}
  ]
}
```

#### Case 4: POI đóng cửa trong ngày đó
```json
{
  "day": "Tuesday",
  "date": "2026-01-14",
  "is_open": false,
  "hours": []
}
```

#### Case 5: POI không có thông tin opening hours
```json
{
  "day": "Monday",
  "date": "2026-01-13",
  "is_open": true,
  "hours": [
    {"start": "00:00", "end": "23:59"}
  ],
  "note": "No opening hours data (assumed always open)"
}
```

## Complete Example Response

```json
{
  "status": "success",
  "query": "Food & Local Flavours,Culture & heritage",
  "user_location": {
    "latitude": 10.774087,
    "longitude": 106.703535
  },
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
      "travel_time_minutes": 25,
      "stay_time_minutes": 125,
      "total_score": 4.5,
      "avg_score": 0.9,
      "efficiency": 2.14,
      "opening_hours_validated": true,
      "is_valid_timing": true,
      "places": [
        {
          "place_id": "df7b73df-00ee-4bd1-bab4-a8f46bb99b8f",
          "place_name": "BÚP Sky Cuisine",
          "poi_type": "Restaurant,Cocktail bar",
          "address": "65-67-69 Nguyễn Thái Bình, Quận 1",
          "lat": 10.7694071,
          "lon": 106.7001448,
          "similarity": 0.835,
          "rating": 0.783,
          "combined_score": 0.814,
          "travel_time_minutes": 7.7,
          "stay_time_minutes": 30,
          "route_id": 1,
          "order": 1,
          "arrival_time": "2026-01-13 08:07:42",
          "opening_hours_today": {
            "day": "Monday",
            "date": "2026-01-13",
            "is_open": true,
            "hours": [
              {"start": "08:00", "end": "22:00"}
            ]
          }
        },
        {
          "place_id": "abc123...",
          "place_name": "Cafe XYZ",
          "poi_type": "Cafe",
          "address": "...",
          "lat": 10.770,
          "lon": 106.700,
          "combined_score": 0.798,
          "travel_time_minutes": 5.2,
          "stay_time_minutes": 30,
          "route_id": 1,
          "order": 2,
          "arrival_time": "2026-01-13 08:42:54",
          "opening_hours_today": {
            "day": "Monday",
            "date": "2026-01-13",
            "is_open": true,
            "hours": [
              {"start": "06:00", "end": "23:00"}
            ]
          }
        }
      ]
    }
  ]
}
```

## Lưu ý Implementation

1. **Chỉ có khi có `current_time`**: 
   - Fields `arrival_time` và `opening_hours_today` chỉ xuất hiện khi request có `current_time`
   - Nếu không có `current_time`, response sẽ như cũ (backward compatible)

2. **Tính toán arrival_time**:
   ```
   POI 1: arrival_time = current_time + travel_time_from_user
   POI 2: arrival_time = POI1_arrival + POI1_stay_time + travel_time_from_POI1
   POI 3: arrival_time = POI2_arrival + POI2_stay_time + travel_time_from_POI2
   ```

3. **Opening hours cho ngày cụ thể**:
   - Dựa trên `arrival_time` để xác định ngày
   - Trích xuất opening hours từ full data cho đúng ngày đó
   - Hỗ trợ cross-day (nếu route kéo dài qua 2 ngày)

## Test

```bash
cd /Users/macbook/Desktop/Kyanon/Kyanon-support-localtion
source ../myenv/bin/activate
python scripts/test_connect/test_opening_hours_response.py
```

## Ứng dụng

Frontend có thể sử dụng để:
1. Hiển thị giờ đến từng POI
2. Hiển thị giờ mở/đóng cửa của POI trong ngày đó
3. Warning nếu POI đóng cửa khi user đến
4. Gợi ý adjust thời gian nếu cần

## Example Frontend Display

```
Route #1 (150 minutes)

1. BÚP Sky Cuisine ⭐ 0.814
   📍 65-67-69 Nguyễn Thái Bình, Quận 1
   🕐 Arrival: 08:07 AM
   🏪 Open: 08:00 - 22:00 (Monday)
   ✅ Will be OPEN when you arrive
   
2. Cafe XYZ ⭐ 0.798
   📍 ...
   🕐 Arrival: 08:42 AM
   🏪 Open: 06:00 - 23:00 (Monday)
   ✅ Will be OPEN when you arrive
```
