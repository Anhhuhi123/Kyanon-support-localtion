# Update POI Endpoint Documentation

## Tổng quan

Endpoint `POST /api/v1/route/update-poi` cho phép thay thế một POI trong route đã có bằng POI khác cùng category, giữ nguyên các POI còn lại.

## Workflow

```
1. User gọi /routes → Tạo route và cache metadata vào Redis
   ↓
2. Redis cache lưu:
   - route_metadata:{user_id}:{route_id} → Thông tin route (POIs + available POIs by category)
   - location:{poi_id} → Thông tin chi tiết từng POI (đã có sẵn)
   ↓
3. User gọi /update-poi → Thay thế POI trong route
   ↓
4. Service logic:
   - Lấy route metadata từ Redis
   - Xác định category của POI cần thay thế
   - Tìm POI khác cùng category từ available POIs
   - Validate opening hours (nếu có current_time)
   - Thay thế POI và update cache
   ↓
5. Response với POI mới và route đã update
```

## Redis Cache Structure

### 1. Route Metadata Cache

**Key:** `route_metadata:{user_id}` ✅ **1 cache duy nhất cho mỗi user**  
**TTL:** 3600 seconds (1 hour)  
**Format:** JSON

```json
{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "routes": {
    "route_0": {
      "pois": [
        {
          "poi_id": "123e4567-e89b-12d3-a456-426614174000",
          "category": "Restaurant"
        },
        {
          "poi_id": "123e4567-e89b-12d3-a456-426614174001",
          "category": "Culture & heritage"
        },
        ...
      ]
    },
    "route_1": {
      "pois": [...]
    },
    "route_2": {
      "pois": [...]
    }
  },
  "available_pois_by_category": {
    "Restaurant": ["poi_id_1", "poi_id_2", "poi_id_3", ...],
    "Culture & heritage": ["poi_id_4", "poi_id_5", ...],
    "Cafe & Bakery": ["poi_id_6", "poi_id_7", ...],
    ...
  }
}
```

**✅ Lợi ích:**
- Chỉ 1 cache cho mỗi user_id, không bị duplicate
- Khi user query lại, cache cũ bị ghi đè → Không tích tụ cache
- Atomic update - tất cả routes được update cùng lúc

### 2. POI Data Cache (Existing)

**Key:** `location:{poi_id}`  
**TTL:** Từ Config.REDIS_CACHE_TTL  
**Format:** JSON

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "Cafe ABC",
  "lat": 10.774087,
  "lon": 106.703535,
  "address": "123 Street",
  "poi_type": "cafe",
  "rating": 4.5,
  "open_hours": [
    {
      "day": "Monday",
      "hours": [{"start": "08:00", "end": "22:00"}]
    },
    ...
  ]
}
```

## API Endpoints

### 1. Create Route (Existing - Enhanced)

**Endpoint:** `POST /api/v1/route/routes`

**Request Body:**
```json
{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "latitude": 10.774087,
  "longitude": 106.703535,
  "transportation_mode": "WALKING",
  "semantic_query": "Food & Local Flavours",
  "current_time": "2026-01-15T12:00:00",
  "max_time_minutes": 180,
  "target_places": 5,
  "max_routes": 3,
  "top_k_semantic": 10
}
```

**Response:**
```json
{
  "status": "success",
  "query": "Food & Local Flavours",
  "routes": [
    {
      "route_id": 0,
      "total_time_minutes": 210,
      "places": [
        {
          "id": "123e4567-e89b-12d3-a456-426614174000",
          "name": "Restaurant ABC",
          "category": "Restaurant",
          "lat": 10.774087,
          "lon": 106.703535,
          ...
        },
        ...
      ]
    }
  ]
}
```

**Changes:**
- ✅ Route metadata được cache vào Redis với key `route_metadata:{user_id}:route_{idx}`
- ✅ Cache bao gồm: POIs trong route + available POIs by category

### 2. Update POI (NEW)

**Endpoint:** `POST /api/v1/route/update-poi`

**Request Body:**
```json
{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "route_id": "route_0",
  "poi_id_to_replace": "123e4567-e89b-12d3-a456-426614174000",
  "current_time": "2026-01-15T12:00:00"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | UUID | Yes | UUID của user |
| route_id | string | Yes | ID của route (vd: "route_0", "route_1") |
| poi_id_to_replace | string | Yes | ID của POI cần thay thế |
| current_time | datetime | No | Thời điểm hiện tại (ISO format) để validate opening hours |

**Response (Success):**
```json
{
  "status": "success",
  "message": "Successfully replaced POI xxx with yyy",
  "old_poi_id": "123e4567-e89b-12d3-a456-426614174000",
  "new_poi": {
    "id": "123e4567-e89b-12d3-a456-426614174010",
    "name": "New Restaurant",
    "category": "Restaurant",
    "lat": 10.774087,
    "lon": 106.703535,
    "address": "456 Street",
    "poi_type": "restaurant",
    "rating": 4.8,
    "open_hours": [...]
  },
  "category": "Restaurant",
  "route_id": "route_0",
  "updated_pois": [
    {"poi_id": "123e4567-e89b-12d3-a456-426614174010", "category": "Restaurant"},
    {"poi_id": "123e4567-e89b-12d3-a456-426614174001", "category": "Culture & heritage"},
    ...
  ]
}
```

**Response (Error):**
```json
{
  "detail": "Route not found in cache: route_metadata:xxx:route_0"
}
```

**Error Cases:**

1. **Route not found in cache:**
   - HTTP 400
   - Message: "Route not found in cache: {cache_key}"
   - Reason: Route đã expired hoặc chưa được tạo

2. **POI not found in route:**
   - HTTP 400
   - Message: "POI {poi_id} not found in route"
   - Reason: POI ID không tồn tại trong route

3. **No alternative POIs:**
   - HTTP 400
   - Message: "No alternative POIs available in category '{category}'"
   - Reason: Không có POI nào khác cùng category

4. **No open POIs:**
   - HTTP 400
   - Message: "No POIs open at {datetime} in category '{category}'"
   - Reason: Không có POI nào mở cửa vào thời gian đó

## Logic Details

### 1. POI Selection Logic

```python
# 1. Lấy category của POI cần thay thế
poi_category = route_metadata['pois'][idx]['category']

# 2. Lấy available POIs cùng category
available_pois = route_metadata['available_pois_by_category'][poi_category]

# 3. Lọc bỏ POIs đã có trong route
available_pois = [p for p in available_pois if p not in current_route_poi_ids]

# 4. Validate opening hours (nếu có current_time)
if current_time:
    available_pois = [p for p in available_pois if TimeUtils.is_open_at_time(p['open_hours'], current_time)]

# 5. Chọn POI đầu tiên (có thể thêm ranking logic sau)
new_poi = available_pois[0]
```

### 2. Category Matching

- POI mới **BẮT BUỘC** phải cùng category với POI bị thay thế
- Category được xác định từ semantic search ban đầu
- Categories có thể có:
  - `Restaurant`
  - `Cafe & Bakery`
  - `Culture & heritage`
  - `Shopping & Souvenirs`
  - `Entertainment`
  - ...

### 3. Opening Hours Validation

```python
# Nếu có current_time, chỉ chọn POI đang mở cửa
if current_time:
    valid_pois = []
    for poi in candidate_pois:
        open_hours = TimeUtils.normalize_open_hours(poi.get('open_hours'))
        if TimeUtils.is_open_at_time(open_hours, current_time):
            valid_pois.append(poi)
```

## Testing

### Run Test Script

```bash
# Make sure server is running
cd /Users/macbook/Desktop/Kyanon/Kyanon-support-localtion
python scripts/test/test_update_poi_api.py
```

### Test Cases

1. **Test 1: Route Search**
   - Tạo route mới với semantic query
   - Verify route metadata được cache

2. **Test 2: Update POI**
   - Thay thế POI đầu tiên trong route
   - Verify POI mới cùng category
   - Verify route metadata được update

3. **Test 3: Error Cases**
   - Invalid route_id
   - Invalid POI ID
   - No alternative POIs

### Manual Testing with cURL

```bash
# 1. Create route
curl -X POST http://localhost:8000/api/v1/route/routes \
  -H "Content-Type: application/json" \
  -d '{
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
  }'

# 2. Update POI (replace {poi_id} with actual ID from step 1)
curl -X POST http://localhost:8000/api/v1/route/update-poi \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
    "route_id": "route_0",
    "poi_id_to_replace": "{poi_id}",
    "current_time": "2026-01-15T12:00:00"
  }'
```

### Check Redis Cache

```bash
# Connect to Redis
redis-cli

# Check route metadata (1 cache duy nhất cho user)
GET route_metadata:816d05bf-5b65-49d2-9087-77c4c83be655

# Check POI data
GET location:{poi_id}

# List all route metadata keys
KEYS route_metadata:*

# Check TTL
TTL route_metadata:816d05bf-5b65-49d2-9087-77c4c83be655
```

## Future Enhancements

### 1. POI Ranking Logic
Thay vì chọn POI đầu tiên, có thể thêm ranking dựa trên:
- Similarity score cao hơn
- Rating cao hơn
- Distance gần hơn với các POI khác trong route
- User preferences

### 2. Multiple POI Updates
Cho phép update nhiều POI cùng lúc trong một request

### 3. Route Optimization
Sau khi update POI, tự động tối ưu lại route (reorder POIs)

### 4. User Feedback
Lưu lại POI đã được replace để tránh gợi ý lại trong lần sau

### 5. Cache Warming
Pre-populate cache cho các routes phổ biến

## Notes

- ✅ Chỉ lưu ID của POI trong route metadata (không lưu full metadata)
- ✅ Sử dụng cache POI hiện có (`location:{poi_id}`) để lấy chi tiết
- ✅ Route metadata cache có TTL 1 giờ
- ✅ POI mới phải cùng category với POI cũ
- ✅ Validate opening hours nếu có `current_time`
- ⚠️ Nếu không tìm thấy POI thay thế phù hợp, trả về error (không fallback)
