# Update POI Feature Implementation Summary

## Tổng quan
Đã hoàn thành việc implement endpoint `POST /api/v1/route/update-poi` để thay thế POI trong route đã có bằng POI khác cùng category.

## Files Modified/Created

### 1. Pydantic Models
**File:** `pydantics/route.py`
- ✅ Thêm `UpdatePOIRequest` model với các fields:
  - `user_id`: UUID
  - `route_id`: string
  - `poi_id_to_replace`: string
  - `current_time`: Optional[datetime]

### 2. Service Layer
**File:** `services/route_search.py`
- ✅ Import `json` để serialize/deserialize Redis data
- ✅ Thêm method `_cache_route_metadata()`:
  - Cache route metadata vào Redis với key `route_metadata:{user_id}:{route_id}`
  - Lưu POIs trong route + available POIs by category
  - TTL: 3600 seconds (1 hour)
- ✅ Thêm method `update_poi_in_route()`:
  - Lấy route metadata từ Redis
  - Xác định category của POI cần thay thế
  - Tìm POI khác cùng category từ available POIs
  - Validate opening hours (nếu có `current_time`)
  - Thay thế POI và update cache
- ✅ Update `build_routes()` để call `_cache_route_metadata()` sau khi build routes

### 3. Router
**File:** `routers/v1/route_api.py`
- ✅ Import `UpdatePOIRequest` từ pydantics
- ✅ Thêm endpoint `POST /update-poi`:
  - Nhận `UpdatePOIRequest`
  - Call `route_service.update_poi_in_route()`
  - Return POI mới và route đã update

### 4. Location Info Service (Enhanced)
**File:** `radius_logic/information_location.py`
- ✅ Update `get_location_by_id()`:
  - Thêm `open_hours` vào query
  - Normalize open_hours với `TimeUtils.normalize_open_hours()`
- ✅ Update `get_locations_by_ids()`:
  - Thêm `open_hours` vào query
  - Normalize open_hours với `TimeUtils.normalize_open_hours()`

### 5. Documentation
**File:** `docs/UPDATE_POI_ENDPOINT.md`
- ✅ API documentation
- ✅ Redis cache structure
- ✅ Workflow explanation
- ✅ Testing guide
- ✅ Error handling

### 6. Test Script
**File:** `scripts/test/test_update_poi_api.py`
- ✅ Test route search và cache metadata
- ✅ Test update POI
- ✅ Test error cases

## Key Features

### 1. Redis Cache Strategy
- **Route Metadata Cache:**
  - Key: `route_metadata:{user_id}:{route_id}`
  - TTL: 3600 seconds
  - Data: POIs trong route + available POIs by category
- **POI Data Cache (Existing):**
  - Key: `location:{poi_id}`
  - Data: Full POI information including open_hours

### 2. POI Selection Logic
1. Lấy category của POI cần thay thế
2. Filter available POIs cùng category
3. Loại bỏ POIs đã có trong route
4. Validate opening hours (nếu có `current_time`)
5. Chọn POI đầu tiên (có thể extend với ranking logic)

### 3. Opening Hours Validation
- Sử dụng `TimeUtils.is_open_at_time()` để check
- Chỉ chọn POI đang mở cửa nếu có `current_time`
- Support POI mở cửa qua đêm

### 4. Error Handling
- Route not found in cache
- POI not found in route
- No alternative POIs available
- No POIs open at specified time

## Redis Cache Structure

```json
{
  "route_metadata:{user_id}:{route_id}": {
    "user_id": "...",
    "route_id": "route_0",
    "pois": [
      {"poi_id": "...", "category": "Restaurant"},
      {"poi_id": "...", "category": "Culture & heritage"}
    ],
    "available_pois_by_category": {
      "Restaurant": ["poi_id_1", "poi_id_2", ...],
      "Culture & heritage": ["poi_id_3", "poi_id_4", ...],
      ...
    }
  }
}
```

## API Example

### Request
```bash
POST /api/v1/route/update-poi
Content-Type: application/json

{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "route_id": "route_0",
  "poi_id_to_replace": "123e4567-e89b-12d3-a456-426614174000",
  "current_time": "2026-01-15T12:00:00"
}
```

### Response
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
    ...
  },
  "category": "Restaurant",
  "route_id": "route_0",
  "updated_pois": [...]
}
```

## Testing

### Run Test Script
```bash
cd /Users/macbook/Desktop/Kyanon/Kyanon-support-localtion
python scripts/test/test_update_poi_api.py
```

### Verify Redis Cache
```bash
redis-cli
GET route_metadata:816d05bf-5b65-49d2-9087-77c4c83be655:route_0
```

## Benefits

1. ✅ **Performance:** Sử dụng Redis cache để tránh query DB nhiều lần
2. ✅ **Consistency:** POI mới luôn cùng category với POI cũ
3. ✅ **Validation:** Check opening hours để đảm bảo POI đang mở cửa
4. ✅ **Scalability:** Chỉ lưu ID, metadata được cache riêng
5. ✅ **User Experience:** Update nhanh, không cần rebuild entire route

## Future Improvements

1. **POI Ranking:** Thêm logic ranking dựa trên similarity, rating, distance
2. **Multiple Updates:** Support update nhiều POI cùng lúc
3. **Route Optimization:** Tự động reorder POIs sau khi update
4. **User Feedback:** Track replaced POIs để improve recommendations
5. **Cache Warming:** Pre-populate cache cho popular routes

## Dependencies

- `asyncpg`: PostgreSQL async driver
- `redis.asyncio`: Redis async client
- `pydantic`: Request validation
- `fastapi`: Web framework
- Custom modules:
  - `utils.time_utils.TimeUtils`: Opening hours logic
  - `radius_logic.information_location.LocationInfoService`: POI data

## Conclusion

Feature đã được implement đầy đủ với:
- ✅ API endpoint working
- ✅ Redis caching strategy
- ✅ POI selection and validation logic
- ✅ Error handling
- ✅ Documentation
- ✅ Test script

Ready for testing and integration! 🚀
