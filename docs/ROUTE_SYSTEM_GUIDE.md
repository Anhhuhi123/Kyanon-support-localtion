# 📍 Hướng Dẫn Hệ Thống Xây Dựng Route

## 📋 Mục Lục
1. [Tổng Quan Hệ Thống](#tổng-quan-hệ-thống)
2. [Các Endpoint API](#các-endpoint-api)
3. [Logic Xử Lý Query](#logic-xử-lý-query)
4. [Quy Luật Chọn POI](#quy-luật-chọn-poi)
5. [Các Trường Hợp Sử Dụng](#các-trường-hợp-sử-dụng)
6. [Quản Lý Cache & Replace Route](#quản-lý-cache--replace-route)

---

## 🎯 Tổng Quan Hệ Thống

### Workflow Tổng Quát
```
1. User gửi request với:
   - Tọa độ hiện tại (latitude, longitude)
   - Phương tiện di chuyển (transportation_mode)
   - Nhu cầu du lịch (semantic_query)
   - Thời gian có (max_time_minutes)
   - Số địa điểm mong muốn (target_places)

2. Hệ thống xử lý:
   ├─ Spatial Search: Tìm POI gần user (PostGIS)
   ├─ Semantic Search: Tìm POI phù hợp nhu cầu (Qdrant)
   ├─ Filter Opening Hours: Lọc POI đang mở cửa (nếu có current_time)
   ├─ Meal Time Detection: Tự động thêm Restaurant nếu trùng giờ ăn
   └─ Route Building: Xây dựng 3 routes tối ưu (Greedy Algorithm)

3. Kết quả trả về:
   - Tối đa 3 routes
   - Mỗi route có 5-7 POI (tùy target_places)
   - Thông tin chi tiết: thời gian di chuyển, lưu trú, rating, địa chỉ...
```

---

## 🛠️ Các Endpoint API

### 1. **POST `/api/v1/route/routes`** - Xây Dựng Routes

#### Request Body
```json
{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "latitude": 21.028511,
  "longitude": 105.804817,
  "transportation_mode": "WALKING",
  "semantic_query": "Food & Local Flavours",
  "current_time": "2026-01-16T08:00:00",
  "max_time_minutes": 300,
  "target_places": 5,
  "max_routes": 3,
  "top_k_semantic": 10,
  "customer_like": true,
  "delete_cache": false,
  "replace_route": null
}
```

#### Các Tham Số

| Tham số | Bắt buộc | Mặc định | Mô tả |
|---------|----------|----------|-------|
| `user_id` | ❌ | null | UUID của user (để cache routes) |
| `latitude` | ✅ | - | Vĩ độ hiện tại |
| `longitude` | ✅ | - | Kinh độ hiện tại |
| `transportation_mode` | ✅ | - | `WALKING/BICYCLING/TRANSIT/FLEXIBLE/DRIVING` |
| `semantic_query` | ✅ | - | Nhu cầu du lịch (xem danh sách bên dưới) |
| `current_time` | ❌ | null | Thời điểm hiện tại (ISO format) - để lọc POI đang mở |
| `max_time_minutes` | ❌ | 180 | Thời gian tối đa (phút) |
| `target_places` | ❌ | 5 | Số địa điểm mỗi route |
| `max_routes` | ❌ | 3 | Số routes tối đa |
| `top_k_semantic` | ❌ | 10 | Số POI từ semantic search |
| `customer_like` | ❌ | false | Tự động thêm Entertainment |
| `delete_cache` | ❌ | false | Xóa cache trước khi build (dành cho tester khi muốn khởi tạo lại chứ ko sẽ tăng route_id lên miết 1 2 3 4 mà ko dừng lại) |
| `replace_route` | ❌ | null | ID route cần thay thế (1, 2, 3) (ko được bỏ vào nếu chưa chạy lần đầu tiên để có route_id )|

#### Tốc Độ Di Chuyển
```python
TRANSPORTATION_SPEEDS = {
    "WALKING": 5 km/h,      # Đi bộ
    "BIKE": 15 km/h,   # Xe bike
    "CAR": 25 km/h,     # Xe car
    "FLEXIBLE": 30 km/h,    # Linh hoạt
}
```

---

### 2. **POST `/api/v1/poi/update-poi`** - Thay Thế POI Trong Route

#### Request Body
```json
{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "route_id": "1",
  "poi_id_to_replace": "123e4567-e89b-12d3-a456-426614174000",
  "current_time": "2026-01-16T10:30:00"
}
```

#### Response - Trả về 3 POI Candidates
```json
{
  "status": "success",
  "message": "Found 3 alternative POI(s) for category 'Restaurant'",
  "old_poi_id": "123e4567-e89b-12d3-a456-426614174000",
  "category": "Restaurant",
  "route_id": "1",
  "candidates": [
    {
      "place_id": "abc...",
      "place_name": "Bún Chả Hương Liên",
      "category": "Restaurant",
      "rating": 4.5,
      "travel_time_minutes": 12.5,
      "stay_time_minutes": 30,
      "arrival_time": "2026-01-16 11:00:00",
      "opening_hours_today": "07:00 - 21:00",
      "distance_changes": {
        "from_prev_old": 0.8,
        "from_prev_new": 1.2,
        "to_next_old": 1.5,
        "to_next_new": 1.8
      },
      "time_changes": {
        "from_prev_old": 9.6,
        "from_prev_new": 14.4,
        "to_next_old": 18.0,
        "to_next_new": 21.6
      }
    },
    // ... 2 POI candidates khác
  ]
}
```

---

### 3. **POST `/api/v1/poi/confirm-replace`** - Xác Nhận Thay Thế POI

#### Request Body
```json
{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "route_id": "1",
  "old_poi_id": "123e4567-e89b-12d3-a456-426614174000",
  "new_poi_id": "abc-def-ghi"
}
```

---

## 🔍 Logic Xử Lý Query

### Danh Sách Category Hỗ Trợ
1. **Food & Local Flavours** → Tự động mở rộng thành:
   - `Cafe & Bakery`
   - `Restaurant`

2. **Culture & heritage**
3. **Nature & View**
4. **Entertainment**
5. **Shopping**
6. **Bar**

### Quy Tắc Xử Lý Query

#### Case 1: Chọn "Food & Local Flavours"
```python
Input: "Food & Local Flavours"
→ Expand: ["Cafe & Bakery", "Restaurant"]

Kết quả:
- Tìm top 10 POI cho "Cafe & Bakery"
- Tìm top 10 POI cho "Restaurant"
- Merge lại (POI nào có similarity cao hơn sẽ được chọn)
- Total: ~15-20 POI unique
```

**Ví dụ Route:**
```
Route 1:
├─ POI 1: Cafe & Bakery (điểm xuất phát)
├─ POI 2: Restaurant
├─ POI 3: Cafe & Bakery
├─ POI 4: Restaurant
└─ POI 5: Cafe & Bakery (điểm kết thúc gần user)
```

#### Case 2: Chọn "Food & Local Flavours" + `customer_like = true`
```python
Input: "Food & Local Flavours", customer_like = true
→ Expand: ["Cafe & Bakery", "Restaurant", "Culture & heritage"]

Logic:
- Nếu chỉ có 1 query "Food & Local Flavours"
- VÀ customer_like = true
- → Tự động thêm "Culture & heritage"

Kết quả:
- Tìm top 10 POI cho "Cafe & Bakery"
- Tìm top 10 POI cho "Restaurant"
- Tìm top 10 POI cho "Culture & heritage"
- Merge lại
- Total: ~20-30 POI unique
```

**Ví dụ Route:**
```
Route 1:
├─ POI 1: Cafe & Bakery
├─ POI 2: Culture & heritage
├─ POI 3: Restaurant
├─ POI 4: Culture & heritage
└─ POI 5: Cafe & Bakery

Route 2:
├─ POI 1: Restaurant
├─ POI 2: Cafe & Bakery
├─ POI 3: Culture & heritage
├─ POI 4: Restaurant
└─ POI 5: Culture & heritage
```

#### Case 3: Chọn Nhiều Category
```python
Input: "Food & Local Flavours, Nature & View"
→ Expand: ["Cafe & Bakery", "Restaurant", "Nature & View"]

Kết quả:
- 3 queries riêng biệt
- Mỗi query tìm top 10
- Total: ~25-30 POI unique
```

**Ví dụ Route:**
```
Route 1:
├─ POI 1: Cafe & Bakery
├─ POI 2: Nature & View
├─ POI 3: Restaurant
├─ POI 4: Nature & View
└─ POI 5: Cafe & Bakery
```

#### Case 4: Meal Time Auto-Detection
```python
Nếu:
- current_time = "2026-01-16T11:30:00"
- max_time_minutes = 180 (3 giờ)
- User KHÔNG chọn "Food & Local Flavours"

→ Hệ thống tự động:
- Phát hiện overlap với lunch (11:30-13:30) hoặc dinner (18:00-20:00)
- Tự động thêm "Restaurant" vào query
- Chèn Restaurant đúng vào meal time window

Ví dụ:
Input: "Culture & heritage"
Time: 11:30 - 14:30
→ Auto expand: ["Culture & heritage", "Restaurant"]
→ Route sẽ có Restaurant ở giữa (khoảng 12:00-13:00)
```

---

## 🎲 Quy Luật Chọn POI (tỉ lệ distance_score, rating_score có thể điều chỉnh)

### 1. POI Đầu Tiên (Starting POI)

**Mục tiêu:** Chọn POI gần user, có rating cao, phù hợp với semantic query ( thể loại phù hợp vơi interest)

**Score Formula:**
```python
combined_score = (
    0.1  * distance_score    +  # 10% - Gần user
    0.45 * similarity_score  +  # 45% - Phù hợp nhu cầu
    0.45 * rating_score         # 45% - Rating cao
)
```

**Ví dụ:**
```python
User location: (21.028511, 105.804817)
Query: "Food & Local Flavours"

POI A: Cafe gần user (0.5km), rating 4.0, similarity 0.85
→ distance_score = 0.95 (rất gần)
→ similarity_score = 0.85
→ rating_score = 0.8 (4.0/5)
→ combined = 0.1*0.95 + 0.45*0.85 + 0.45*0.8 = 0.8375

POI B: Restaurant xa user (2km), rating 4.8, similarity 0.92
→ distance_score = 0.75
→ similarity_score = 0.92
→ rating_score = 0.96
→ combined = 0.1*0.75 + 0.45*0.92 + 0.45*0.96 = 0.921

→ Chọn POI B (Restaurant)
```

**Lưu ý đặc biệt:**
- Luôn validate opening hours (nếu có `current_time`) (luôn đảm bảo thời gian đi tới phù hợp với thời gian mở cửa)

---

### 2. POI Giữa (Middle POIs)

**Mục tiêu:** 
- Xen kẽ category (không lặp liên tiếp)
- Hướng về phía user (bearing score)
- Balance giữa similarity và rating

**Score Formula - Khi Similarity (tức là độ phù hợp của POI với option interest của người dùng) ≥ 0.8:**
```python
combined_score = (
    0.15 * distance_score    +  # 15% - Không quá xa
    0.30 * similarity_score  +  # 30% - Phù hợp
    0.30 * rating_score      +  # 30% - Rating tốt
    0.25 * bearing_score        # 25% - Hướng về user
)
```

**Score Formula - Khi Similarity < 0.8:**
```python
combined_score = (
    0.25 * distance_score    +  # 25% - Ưu tiên gần hơn
    0.10 * similarity_score  +  # 10% - Giảm trọng số
    0.40 * rating_score      +  # 40% - Ưu tiên rating
    0.25 * bearing_score        # 25% - Hướng về user
)
```

**Bearing Score (công thức tạo vòng cung):**
```python
bearing_score = 1 - (angle_diff / 180)

Ví dụ:
- Bearing về user: 90° (Đông)
- POI candidate: 95° (hướng Đông Đông Nam)
- angle_diff = |95 - 90| = 5°
- bearing_score = 1 - (5/180) = 0.972 (rất tốt)

- POI candidate: 270° (hướng Tây)
- angle_diff = |270 - 90| = 180°
- bearing_score = 1 - (180/180) = 0 (tệ)
```

**Quy Tắc Xen Kẽ Category:**
```python
Ví dụ có 3 categories: [Cafe, Restaurant, Culture]

Category sequence: [Cafe, Restaurant, Cafe, Culture, Cafe]
                     ✅     ✅        ✅     ✅      ✅
# Không lặp liên tiếp

Category sequence: [Cafe, Cafe, Restaurant, Culture, Cafe]
                     ✅     ❌  # KHÔNG HỢP LỆ - Cafe lặp

Ngoại lệ:
- Nếu hết POI của category khác → Được phép lặp
- Meal time Restaurant → Chèn đúng vào thời gian ăn (không theo quy tắc xen kẽ)
```

---

### 3. POI Cuối Cùng (Last POI)

**Mục tiêu:** Chọn POI GẦN USER nhất để kết thúc route

**Thuật toán:** 
1. Xác định bán kính tìm kiếm từ gần đến xa:
   ```python
   thresholds = [0.2, 0.4, 0.6, 0.8, 1.0]  # % của max_radius
   ```

2. Tìm POI trong mỗi threshold:
   ```python
   max_radius = 10 km  # Xa nhất từ user
   
   Lần 1: Tìm POI trong 2km (0.2 * 10)
   → Nếu có POI → Chọn
   → Nếu không → Tìm tiếp
   
   Lần 2: Tìm POI trong 4km (0.4 * 10)
   → ...
   ```

**Score Formula:**
```python
combined_score = (
    0.4 * distance_score    +  # 40% - Ưu tiên gần user
    0.3 * similarity_score  +  # 30% - Vẫn phù hợp nhu cầu
    0.3 * rating_score         # 30% - Rating tốt
)
```

**Ví dụ:**
```python
User location: (21.028511, 105.804817)
Current position: POI 4 at (21.045, 105.820)
Query: "Food & Local Flavours"

POI A: Cafe, 0.8km từ user, similarity 0.75, rating 3.8
→ distance_score = 0.92
→ similarity_score = 0.75
→ rating_score = 0.76
→ combined = 0.4*0.92 + 0.3*0.75 + 0.3*0.76 = 0.821

POI B: Restaurant, 1.5km từ user, similarity 0.88, rating 4.5
→ distance_score = 0.85
→ similarity_score = 0.88
→ rating_score = 0.9
→ combined = 0.4*0.85 + 0.3*0.88 + 0.3*0.9 = 0.874

→ Chọn POI B (gần user, rating cao hơn)
```

---

## 💼 Các Trường Hợp Sử Dụng

### Case 1: Du Lịch Ẩm Thực Đơn Giản
```json
{
  "semantic_query": "Food & Local Flavours",
  "transportation_mode": "WALKING",
  "max_time_minutes": 180,
  "target_places": 5
}
```

**Kết quả:**
- 1 routes
- Route có 5 POI xen kẽ Cafe & Restaurant
- Thời gian: ~3 giờ
- Không lọc opening hours (không có current_time)

---

### Case 2: Du Lịch Ẩm Thực + Văn Hóa
```json
{
  "semantic_query": "Food & Local Flavours",
  "customer_like": true,
  "current_time": "2026-01-16T08:00:00",
  "max_time_minutes": 360,
  "target_places": 7
}
```

**Kết quả:**
- Expand thành: `[Cafe & Bakery, Restaurant, Culture & heritage]`
- routes, mỗi route n POI
- Xen kẽ 3 loại category
- Lọc POI đang mở cửa lúc 8:00 sáng
- Thời gian: ~6 giờ

---

### Case 3: Du Lịch Buổi Trưa (Meal Time Auto-Insert)
```json
{
  "semantic_query": "Culture & heritage",
  "current_time": "2026-01-16T10:00:00",
  "max_time_minutes": 240,
  "target_places": 6
}
```

**Kết quả:**
- Phát hiện overlap với lunch time (11:30-13:30)
- Auto expand: `[Culture & heritage, Restaurant]`
- Route sẽ có Restaurant chèn vào khoảng 12:00-13:00
- Thời gian: ~4 giờ

**Ví dụ Route:**
```
Start: 10:00
├─ 10:00-10:20: Di chuyển đến POI 1
├─ 10:20-10:50: Culture POI 1 (30 phút)
├─ 10:50-11:05: Di chuyển đến POI 2
├─ 11:05-11:35: Culture POI 2 (30 phút)
├─ 11:35-12:00: Di chuyển đến Restaurant
├─ 12:00-12:50: Restaurant ← Meal time
├─ 12:50-13:10: Di chuyển đến POI 4
├─ 13:10-13:40: Culture POI 4 (30 phút)
└─ Finish: ~14:00
```

---

### Case 4: Du Lịch Nhiều Loại
```json
{
  "semantic_query": "Food & Local Flavours, Nature & View, Shopping",
  "transportation_mode": "DRIVING",
  "max_time_minutes": 480,
  "target_places": 8
}
```

**Kết quả:**
- Expand: `[Cafe & Bakery, Restaurant, Nature & View, Shopping]`
- 4 categories
- Mỗi route n POI xen kẽ 4 loại
- Driving speed (40 km/h) → Có thể đi xa hơn

---

## 🗄️ Quản Lý Cache & Replace Route

### Cache Structure
```json
{
  "user_id": "816d05bf-5b65-49d2-9087-77c4c83be655",
  "transportation_mode": "WALKING",
  "routes": {
    "1": {
      "pois": [
        {"poi_id": "abc...", "category": "Cafe & Bakery"},
        {"poi_id": "def...", "category": "Restaurant"},
        ...
      ]
    },
    "2": {...},
    "3": {...}
  },
  "available_pois_by_category": {
    "Cafe & Bakery": ["id1", "id2", "id3", ...],
    "Restaurant": ["id4", "id5", ...],
    ...
  },
  "replaced_pois_by_category": {
    "Restaurant": ["id_old1", "id_old2"]
  }
}
```

### Delete Cache
```json
{
  "delete_cache": true,
  "...other params..."
}
```

**Hành vi:**
1. Xóa cache của user
2. Tiếp tục build routes từ đầu
3. Trả về 3 routes mới

---

### Replace Route
```json
{
  "replace_route": 1,
  "...other params..."
}
```

**Hành vi:**
1. Kiểm tra route 1 có tồn tại trong cache
2. Gọi `build_routes` với `max_routes = 2` (tạo routes 1, 2)
3. Lấy route 2 từ kết quả
4. **Xóa route 1** khỏi cache
5. **Chỉ lưu route 2** (tiết kiệm bộ nhớ)
6. Trả về route 2

**Logic tiết kiệm bộ nhớ:**
```
replace_route = 1 → Build route 2, xóa route 1, chỉ lưu route 2
replace_route = 2 → Build route 3, xóa route 2, chỉ lưu route 3
replace_route = 3 → Build route 4, xóa route 3, chỉ lưu route 4
...
```

---

## 📊 Thống Kê & Metrics

### Response Time Breakdown
```json
{
  "total_execution_time_seconds": 2.456,
  "timing_breakdown": {
    "spatial_search_seconds": 0.123,
    "embedding_seconds": 0.234,
    "qdrant_search_seconds": 0.345,
    "db_query_seconds": 0.156,
    "route_building_seconds": 1.598
  }
}
```

### Route Metrics
```json
{
  "route_id": 1,
  "total_time_minutes": 215,
  "travel_time_minutes": 65,
  "stay_time_minutes": 150,
  "total_score": 4.3,
  "avg_score": 0.86,
  "efficiency": 2.0,  // total_score / (total_time_minutes / 100)
  "places": [...]
}
```

---

## 🔧 Best Practices

### 1. Lựa Chọn Transportation Mode
- **WALKING** (5 km/h): Khu phố cổ, khoảng cách ngắn (<5km)
- **BICYCLING** (15 km/h): Du lịch trung bình (5-15km)
- **DRIVING** (40 km/h): Du lịch xa, nhiều điểm (>15km)

### 2. Thiết Lập Thời Gian
- **Buổi sáng** (3-4h): `max_time_minutes: 180-240`
- **Cả ngày** (6-8h): `max_time_minutes: 360-480`
- **Cuối tuần** (8-10h): `max_time_minutes: 480-600`

### 3. Số Lượng POI
- **Ngắn ngày**: `target_places: 3-5`
- **Trung bình**: `target_places: 5-7`
- **Cả ngày**: `target_places: 7-10`

### 4. Sử Dụng Current Time
- ✅ **Nên dùng** nếu muốn lọc POI đang mở cửa
- ✅ **Nên dùng** để kích hoạt meal time auto-insert
- ❌ **Không dùng** nếu chỉ cần gợi ý tổng quát

---

## 📞 Support & Contact

Nếu có thắc mắc về API, vui lòng liên hệ team phát triển.

---

**Last Updated:** January 16, 2026
