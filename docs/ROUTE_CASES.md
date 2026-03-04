# 📍 Tất Cả Trường Hợp Xây Dựng Route

> Tài liệu này mô tả chi tiết **mọi trường hợp có thể xảy ra** trong quá trình xây dựng route,
> bao gồm logic chọn POI đầu/giữa/cuối, meal-time insertion, cafe-sequence, fallback, và validation.

---

## 📋 Mục Lục
1. [Chế Độ Build (Build Mode)](#1-chế-độ-build-build-mode)
2. [Validation Đầu Vào](#2-validation-đầu-vào)
3. [Phân Tích Meal Requirements](#3-phân-tích-meal-requirements)
4. [Chọn POI Đầu Tiên](#4-chọn-poi-đầu-tiên)
5. [Chọn POI Giữa (Middle POIs)](#5-chọn-poi-giữa-middle-pois)
6. [Chọn POI Cuối](#6-chọn-poi-cuối)
7. [Cafe-Sequence Logic](#7-cafe-sequence-logic)
8. [Category Alternation (Xen Kẽ)](#8-category-alternation-xen-kẽ)
9. [Fallback Logic](#9-fallback-logic)
10. [Validation Thời Gian (Time Budget)](#10-validation-thời-gian-time-budget)
11. [Tổng Hợp Tất Cả Trường Hợp](#11-tổng-hợp-tất-cả-trường-hợp)

---

## 1. Chế Độ Build (Build Mode)

Hệ thống có **2 chế độ xây dựng route** được kiểm soát bởi tham số `duration_mode`:

| Tham số | Chế độ | Builder | Số POI |
|---------|--------|---------|--------|
| `duration_mode = false` (mặc định) | **Target Mode** | `TargetRouteBuilder` | Cố định = `target_places` |
| `duration_mode = true` | **Duration Mode** | `DurationRouteBuilder` | Linh hoạt, tùy time budget |

### 1.1 Target Mode (FOR LOOP)

```
Cấu trúc: POI đầu → (target_places - 2) POI giữa → POI cuối

Ví dụ target_places = 5:
[POI_first] → [POI_2] → [POI_3] → [POI_4] → [POI_last]
      1 POI       3 POI giữa (FOR LOOP 3 lần)      1 POI
```

- Luôn cố gắng tạo đúng `target_places` POI.
- Nếu không đủ POI hoặc vượt time budget → trả về `None`.

### 1.2 Duration Mode (WHILE LOOP)

```
Stop condition: remaining_time < 30% max_time_minutes

Ví dụ max_time = 180 phút:
- Dừng khi remaining_time < 54 phút
- Route có thể có 3, 5, 7... POI tùy vào time budget
```

- Linh hoạt về số POI.
- Mỗi vòng loop: kiểm tra `remaining_time < 30%` → nếu đúng thì **break** và chọn POI cuối.
- Safety limit: số vòng lặp tối đa = `len(places)` để tránh infinite loop.

---

## 2. Validation Đầu Vào

Trước khi bắt đầu build route, hệ thống kiểm tra:

### Case 2.1 – Danh sách POI rỗng
```python
if not places:
    return None  # ❌ Không build
```

### Case 2.2 – Không đủ POI để xen kẽ category
```python
# Đếm số POI theo category
# Nếu category có nhiều nhất chỉ có <= 1 POI → không build
if max_count_per_category <= 1:
    return None  # ❌ Không build
```
> **Lý do:** Cần ít nhất 2 POI/category để tạo alternation pattern hợp lệ.

### Case 2.3 – Target Mode: target_places > số POI
```python
if target_places > len(places):
    return None  # ❌ Không đủ POI để điền vào route
```

---

## 3. Phân Tích Meal Requirements

Hàm `analyze_meal_requirements()` quyết định có cần **tự động chèn Restaurant** vào route không.

### Case 3.1 – Có "Cafe & Bakery" trong danh sách POI
```
Input categories: ["Cafe & Bakery", "Culture & heritage"]

→ should_insert_restaurant_for_meal = False
→ Không chèn Restaurant tự động
→ Lý do: Cafe & Bakery đã có thức ăn nhẹ đủ thay thế bữa ăn
```

### Case 3.2 – Không có "Cafe & Bakery", không có "Restaurant"
```
Input categories: ["Culture & heritage", "Nature & View"]

→ should_insert_restaurant_for_meal = False
→ Không chèn Restaurant tự động
→ Lý do: Không có Restaurant trong pool POI → không thể chèn
```

### Case 3.3 – Không có "Cafe & Bakery", CÓ "Restaurant", KHÔNG CÓ current_time
```
Input categories: ["Culture & heritage", "Restaurant"]
current_datetime = None

→ should_insert_restaurant_for_meal = False
→ Không chèn Restaurant tự động
→ Lý do: Không biết thời gian → không thể detect meal window
```

### Case 3.4 – Không có "Cafe & Bakery", CÓ "Restaurant", CÓ current_time, KHÔNG overlap meal
```
Input categories: ["Culture & heritage", "Restaurant"]
current_datetime = "2026-01-16T15:00:00"
max_time_minutes = 120 (2 giờ → kết thúc 17:00)

→ Lunch window: 11:00-14:00, Dinner window: 17:00-20:00
→ Route time range: 15:00 - 17:00
→ Overlap với lunch: 0 phút (đã qua)
→ Overlap với dinner: 0 phút (17:00 bắt đầu, chưa đủ 60 phút)
→ should_insert_restaurant_for_meal = False
```

### Case 3.5 – Overlap với LUNCH >= 60 phút ✅
```
Input categories: ["Culture & heritage", "Restaurant"]
current_datetime = "2026-01-16T10:00:00"
max_time_minutes = 180 (kết thúc ~13:00)

→ Lunch window: 11:00-14:00
→ Overlap: 13:00 - 11:00 = 120 phút >= 60 phút ✅
→ need_lunch_restaurant = True
→ should_insert_restaurant_for_meal = True
→ Hệ thống sẽ ép chèn 1 Restaurant vào lúc khoảng 12:00
```

### Case 3.6 – Overlap với DINNER >= 60 phút ✅
```
Input categories: ["Culture & heritage", "Restaurant"]
current_datetime = "2026-01-16T16:00:00"
max_time_minutes = 240 (kết thúc ~20:00)

→ Dinner window: 17:00-20:00
→ Overlap: 20:00 - 17:00 = 180 phút >= 60 phút ✅
→ need_dinner_restaurant = True
→ should_insert_restaurant_for_meal = True
→ Hệ thống sẽ ép chèn 1 Restaurant vào khoảng 18:00
```

### Case 3.7 – Overlap với CẢ HAI meal windows
```
Input categories: ["Culture & heritage", "Restaurant"]
current_datetime = "2026-01-16T10:00:00"
max_time_minutes = 600 (10 giờ → kết thúc ~20:00)

→ need_lunch_restaurant = True
→ need_dinner_restaurant = True
→ Hệ thống sẽ chèn 2 Restaurant: 1 cho lunch + 1 cho dinner
```

### Case 3.8 – Category "Cafe" (không phải "Cafe & Bakery") → Bật Cafe-Sequence
```
Input categories: [..., "Cafe"]

→ should_insert_cafe = True
→ "Cafe" sẽ KHÔNG tham gia alternation thông thường
→ Thay vào đó chèn theo sequence: sau mỗi 2 POI không phải Cafe/Restaurant
→ Xem chi tiết tại Section 7
```

---

## 4. Chọn POI Đầu Tiên

### Score Formula (POI đầu)
```python
FIRST_POI_WEIGHTS = {
    "distance": 0.5,     # 50% – Ưu tiên gần user
    "similarity": 0.1,   # 10% – Phù hợp semantic query
    "rating": 0.4        # 40% – Rating cao
}
combined_score = 0.5 * distance_score + 0.1 * similarity_score + 0.4 * rating_score
```

### Case 4.1 – first_place_idx được chỉ định
```python
if first_place_idx is not None:
    return first_place_idx  # Dùng ngay, bỏ qua mọi filter
```
> Dùng khi build nhiều routes với starting POI khác nhau để tạo sự đa dạng.

### Case 4.2 – Không có meal requirement (bình thường)
```
→ Xét tất cả POI có opening hours hợp lệ (nếu có current_datetime)
→ Bỏ "Cafe" nếu should_insert_cafe = True (cafe chỉ chèn theo sequence, không làm POI đầu)
→ Chọn POI có combined_score cao nhất
```

### Case 4.3 – Có meal requirement, current_time ĐÃ TRONG meal window
```
Ví dụ: current_datetime = "12:30" → đang trong lunch window (11:00-14:00)

→ BẮT BUỘC chọn Restaurant làm POI đầu
→ Loại tất cả POI không phải Restaurant khỏi candidates
→ Nếu không có Restaurant khả dụng → trả về None (không build route)
```

### Case 4.4 – Có meal requirement, current_time CHƯA TỚI meal window
```
Ví dụ: current_datetime = "09:00", lunch window bắt đầu từ "11:00"

→ LOẠI tất cả Restaurant khỏi candidates (giữ cho meal time sau)
→ Chọn POI thuộc category khác có combined_score cao nhất
```

### Case 4.5 – Có should_insert_cafe = True
```
→ Loại tất cả "Cafe" khỏi candidates cho vị trí POI đầu
→ Lý do: Cafe chỉ được chèn sau mỗi 2 POI không phải Cafe/Restaurant
→ Nếu tất cả POI là "Cafe" → trả về None
```

### Case 4.6 – current_datetime có nhưng POI đóng cửa
```
→ Tính arrival_time = current_datetime + travel_time (từ user đến POI)
→ Validate: is_poi_available_at_time(place, arrival_time)
→ POI đóng cửa tại arrival_time → bỏ qua (continue)
→ Nếu tất cả POI đóng cửa → trả về None
```

---

## 5. Chọn POI Giữa (Middle POIs)

### Score Formula (POI giữa)

**Khi similarity >= 0.8:**
```python
MIDDLE_POI_WEIGHTS_HIGH_SIMILARITY = {
    "distance": 0.40,  # 40% – Không quá xa
    "similarity": 0.10, # 10% – Phù hợp
    "rating": 0.25,    # 25% – Rating tốt
    "bearing": 0.25    # 25% – Hướng về user (tránh zíc zắc)
}
```

**Khi similarity < 0.8:**
```python
MIDDLE_POI_WEIGHTS_LOW_SIMILARITY = {
    "distance": 0.40,  # 40% – Ưu tiên gần hơn
    "similarity": 0.10, # 10% – Giảm trọng số
    "rating": 0.25,    # 25% – Ưu tiên rating
    "bearing": 0.25    # 25% – Hướng về user
}
```

**Bearing Score:**
```python
bearing_score = 1.0 - (bearing_diff / 180.0)
# bearing_diff = 0°   → score = 1.0 (cùng hướng, tốt nhất)
# bearing_diff = 90°  → score = 0.5 (vuông góc)
# bearing_diff = 180° → score = 0.0 (ngược hướng, xấu nhất)
```

### Các Filters Áp Dụng Cho POI Giữa

Mỗi candidate phải pass **6 filters** sau:

| Filter | Điều kiện loại |
|--------|---------------|
| **Filter 1** | POI đã có trong route (visited) |
| **Filter 2** | POI là Restaurant + `exclude_restaurant = True` (đang giữ cho meal time) |
| **Filter 3** | Category không khớp `required_category` (nếu đang ép category) |
| **Filter 4** | 2 POI liên tiếp cùng loại đồ ăn (e.g., Phở → Bún chả) |
| **Filter 5** | POI đóng cửa tại estimated arrival time |
| **Filter 6** | Vượt time budget: `travel + stay + estimated_return > max_time` |

---

### Case 5.1 – Đang trong meal window + chưa insert Restaurant cho bữa đó
```
arrival_at_next nằm trong lunch window (11:00-14:00)
VÀ need_lunch_restaurant = True
VÀ lunch_restaurant_inserted = False

→ required_category = "Restaurant"
→ exclude_restaurant = False (override)
→ target_meal_type = "lunch"
→ Chọn Restaurant có combined_score cao nhất
→ Sau khi chọn: lunch_restaurant_inserted = True
```

### Case 5.2 – Đang trong dinner window + chưa insert Restaurant cho bữa đó
```
arrival_at_next nằm trong dinner window (17:00-20:00)
VÀ need_dinner_restaurant = True
VÀ dinner_restaurant_inserted = False

→ required_category = "Restaurant"
→ exclude_restaurant = False (override)
→ target_meal_type = "dinner"
→ Tương tự Case 5.1
```

### Case 5.3 – Đã insert đủ cả 2 bữa
```
lunch_restaurant_inserted = True
dinner_restaurant_inserted = True

→ exclude_restaurant = True (không chọn Restaurant thêm nữa)
→ Tiếp tục bình thường với các category khác
```

### Case 5.4 – Ngoài meal window + có meal requirement
```
arrival_at_next KHÔNG trong bất kỳ meal window nào

→ exclude_restaurant = True (giữ Restaurant cho meal time sau)
→ required_category = category theo alternation (không ép Restaurant)
```

### Case 5.5 – Cafe-sequence triggered (cafe_counter >= 2)
```
should_insert_cafe = True
cafe_counter = 2 (đã qua 2 POI không phải Cafe/Restaurant)
Không đang trong meal window

→ required_category = "Cafe"
→ exclude_restaurant = False (override)
→ Tìm "Cafe" (exact match, KHÔNG phải "Cafe & Bakery")
```

### Case 5.6 – Cafe-sequence triggered nhưng đang trong meal window (bị block)
```
should_insert_cafe = True
cafe_counter >= 2
Nhưng arrival_at_next đang trong meal window

→ Café-sequence bị BLOCK
→ required_category = category theo meal priority hoặc alternation
→ Không chèn Cafe ở bước này
```

### Case 5.7 – Alternation bình thường (không có ép đặc biệt)
```
Ví dụ: all_categories = ["Culture & heritage", "Restaurant", "Cafe & Bakery"]
Nếu bật cafe-sequence: alternation_categories = ["Culture & heritage", "Restaurant"]
category_sequence[-1] = "Culture & heritage"

→ required_category = "Restaurant" (phần tử kế tiếp trong vòng luân phiên)
→ Nếu last_category không có trong alternation_categories → chọn phần tử đầu
```

### Case 5.8 – Không có candidates với required_category → Fallback
```
→ Bỏ required_category constraint
→ Tìm lại không ép category
→ Fallback vẫn giữ: exclude_restaurant, filter đóng cửa, time budget
→ Fallback vẫn KHÔNG chọn "Cafe" nếu cafe_counter < 2 và should_insert_cafe = True
→ Nếu vẫn không có → trả về None (route dừng lại)
```

---

## 6. Chọn POI Cuối

### Score Formula (POI cuối)
```python
LAST_POI_WEIGHTS = {
    "distance": 0.6,    # 60% – Ưu tiên gần user (giảm return time)
    "similarity": 0.1,  # 10% – Vẫn phù hợp nhu cầu
    "rating": 0.3       # 30% – Rating tốt
}
# distance_score = 1 - (dist_to_user / max_distance)
```

### Chiến Lược Tìm Kiếm Theo Radius Threshold
```python
LAST_POI_RADIUS_THRESHOLDS = [0.2, 0.4, 0.6, 0.8, 1.0]
# Mỗi threshold = threshold_multiplier * max_radius

# Ví dụ max_radius = 5km:
# Lần 1: Tìm trong vòng 1km (20%)   → Nếu tìm được → Chọn luôn
# Lần 2: Tìm trong vòng 2km (40%)   → Nếu tìm được → Chọn luôn
# Lần 3: Tìm trong vòng 3km (60%)   → ...
# Lần 4: Tìm trong vòng 4km (80%)   → ...
# Lần 5: Tìm trong vòng 5km (100%)  → Tìm hết tầm
```

### Case 6.1 – POI cuối tìm thấy trong threshold nhỏ
```
→ Ưu tiên POI gần user nhất để về nhanh
→ Chọn POI có combined_score cao nhất trong threshold đó
→ Dừng và không thử threshold lớn hơn
```

### Case 6.2 – POI cuối là Restaurant trong meal window đã insert
```
arrival tại POI cuối rơi vào lunch window
VÀ lunch_restaurant_inserted = True

→ Bỏ POI đó (reasons: "lunch_already_inserted")
→ Tránh insert 2 lần cùng 1 bữa ăn
```

### Case 6.3 – POI cuối là Restaurant NGOÀI meal window
```
arrival tại POI cuối KHÔNG nằm trong bất kỳ meal window nào

→ Bỏ POI đó (reasons: "not_meal_time")
→ Lý do: Restaurant chỉ được chọn khi đúng giờ ăn
```

### Case 6.4 – POI cuối vượt time budget
```
total_travel + stay + travel_to_poi + stay_at_poi + return_to_user > max_time_minutes

→ Bỏ POI đó (reasons: "time(...>...)")
```

### Case 6.5 – POI cuối đóng cửa khi đến
```
→ Bỏ POI đó (reasons: "closed@HH:MM")
```

### Case 6.6 – Không tìm được POI cuối ở bất kỳ threshold nào
```
→ Trả về None
→ Route không có POI cuối nhưng vẫn được xử lý tiếp
→ (Route vẫn hợp lệ nếu đủ min POI)
```

---

## 7. Cafe-Sequence Logic

> Chỉ áp dụng khi có **category "Cafe"** (phân biệt với "Cafe & Bakery"):
> - **"Cafe & Bakery"** → thuộc Food & Local Flavours, xen kẽ bình thường trong alternation.
> - **"Cafe"** → chỉ chèn theo sequence (cứ 2 POI không phải Cafe/Restaurant thì chèn 1).

### Quy Luật Cafe Counter

```
cafe_counter = 0  ← Reset khi chọn Restaurant hoặc Cafe
cafe_counter += 1 ← Tăng khi chọn bất kỳ category khác (Culture, Nature, Shopping...)
cafe_counter >= 2 → Trigger: chèn Cafe ở vị trí tiếp theo (nếu không trong meal window)
```

### Case 7.1 – Khởi tạo cafe_counter từ POI đầu
```
POI đầu là "Restaurant" hoặc "Cafe" → cafe_counter = 0
POI đầu là category khác           → cafe_counter = 1
```

### Case 7.2 – Chuỗi POI thông thường với café
```
Route đang build:
[Culture] → [Nature] → [Cafe] → [Culture] → [Nature] → [Cafe] → ...
counter:  1           2         0            1           2         0

Giải thích:
- Sau Culture: counter = 1
- Sau Nature: counter = 2 ≥ 2 → trigger Cafe
- Sau Cafe: counter = 0 (reset)
- Lặp lại...
```

### Case 7.3 – Cafe-sequence bị block bởi meal window
```
cafe_counter = 2, trong lunch window

→ Không chèn Cafe
→ Chèn Restaurant thay thế (meal priority cao hơn)
→ cafe_counter = 0 (reset vì Restaurant)
```

### Case 7.4 – Không có "Cafe" nào còn khả dụng trong pool
```
cafe_counter >= 2 nhưng tất cả "Cafe" đã visited hoặc đóng cửa

→ Fallback: chọn category khác theo alternation
→ cafe_counter tiếp tục tăng
```

---

## 8. Category Alternation (Xen Kẽ)

### Nguyên Tắc
```
alternation_categories = all_categories - ["Cafe"] (nếu should_insert_cafe = True)
Luân phiên theo vòng tròn dựa trên category của POI vừa chọn
```

### Case 8.1 – 2 Categories
```
alternation_categories = ["Culture & heritage", "Restaurant"]

Chuỗi: Culture → Restaurant → Culture → Restaurant → ...
```

### Case 8.2 – 3 Categories
```
alternation_categories = ["Cafe & Bakery", "Restaurant", "Nature & View"]

Chuỗi: Cafe & Bakery → Restaurant → Nature & View → Cafe & Bakery → ...
```

### Case 8.3 – Category của POI vừa chọn không có trong alternation_categories
```
last_category = "Cafe" (đã bị loại khỏi alternation)
→ ValueError khi index()
→ Fallback: chọn alternation_categories[0]
```

### Case 8.4 – Single category
```
alternation_categories = ["Culture & heritage"]
→ Chỉ có 1 category → (0 + 1) % 1 = 0 → luôn chọn lại element đầu
→ Mọi POI giữa đều là "Culture & heritage"
```

### Case 8.5 – all_categories rỗng
```
→ alternation_categories = []
→ required_category = None (không ép category gì)
→ Chọn bất kỳ POI nào pass các filters khác
```

---

## 9. Fallback Logic

Hệ thống có 3 cấp fallback:

### Fallback Cấp 1 – Middle POI không có candidate với required_category
```python
# Bỏ constraint category, tìm lại
# VẪN giữ: exclude_restaurant, filter đóng cửa, time budget
# VẪN giữ: cafe-sequence check (không chọn Cafe nếu counter < 2)
```

### Fallback Cấp 2 – Middle POI không tìm được candidate nào
```
→ _select_middle_poi trả về None
→ Target mode: break out of FOR LOOP sớm → route có ít hơn target_places POI
→ Duration mode: break WHILE LOOP → chuyển sang chọn POI cuối
```

### Fallback Cấp 3 – Toàn bộ route không feasible
```
Xảy ra khi:
- Không đủ POI (< 2 POI total)
- Time budget quá nhỏ
- Tất cả POI đóng cửa

→ build_route trả về None
→ Hệ thống bỏ qua route này, thử first_place_idx khác
```

---

## 10. Validation Thời Gian (Time Budget)

### Mỗi POI giữa phải pass:
```python
temp_travel + temp_stay + estimated_return <= max_time_minutes
# estimated_return = travel_time từ POI này quay về user location
```

### POI cuối phải pass:
```python
total_travel + stay_at_last + return_to_user <= max_time_minutes
```

### Sau khi hoàn thành route:
```python
total_time = total_travel_time + total_stay_time
if total_time > max_time_minutes:
    return None  # Route không feasible
```

### Duration Mode – Stop Condition:
```python
remaining_time = max_time_minutes - (total_travel_time + total_stay_time)
if remaining_time < max_time_minutes * 0.3:
    break  # Chọn POI cuối
```

---

## 11. Tổng Hợp Tất Cả Trường Hợp

### Ma Trận Trường Hợp – Chọn POI Đầu

| current_time | Meal Requirement | Vị trí time | Kết quả |
|---|---|---|---|
| None | - | - | Chọn POI bất kỳ (trừ Cafe nếu cafe-sequence) theo combined_score |
| Có | Không | - | Chọn POI bất kỳ, validate opening hours |
| Có | Có | Đã trong meal window | **BẮT BUỘC Restaurant** |
| Có | Có | Chưa tới meal window | Loại Restaurant, chọn category khác |

### Ma Trận Trường Hợp – Chọn POI Giữa

| Meal Status | Cafe Counter | Vị trí time | Kết quả |
|---|---|---|---|
| Không cần meal | < 2 | - | Alternation bình thường |
| Không cần meal | >= 2 | - | Chèn Cafe (cafe-sequence) |
| Chưa insert lunch | - | Trong lunch window | **Chèn Restaurant (lunch)** |
| Chưa insert dinner | - | Trong dinner window | **Chèn Restaurant (dinner)** |
| Đã insert đủ | - | - | exclude_restaurant = True, alternation bình thường |
| Chưa insert | >= 2 | Trong meal window | Meal priority thắng, **không chèn Cafe** |

### Ma Trận Trường Hợp – Kết Quả Build Route

| Điều kiện | Kết quả |
|---|---|
| `places` rỗng | `None` |
| Mỗi category có <= 1 POI | `None` |
| Target mode: `target_places > len(places)` | `None` |
| Không tìm được POI đầu | `None` |
| `total_time > max_time_minutes` (sau build xong) | `None` |
| Duration mode: đủ thời gian | Route với N POI linh hoạt |
| Target mode: đủ POI và time | Route với đúng `target_places` POI |
| Middle POI không tìm được (fallback hết) | Route với ít POI hơn dự kiến (target mode) hoặc dừng sớm (duration) |

---

## 📝 Lưu Ý Quan Trọng

1. **"Cafe" ≠ "Cafe & Bakery"**:
   - `"Cafe"` → trigger cafe-sequence (chèn theo counter)
   - `"Cafe & Bakery"` → xen kẽ bình thường trong alternation

2. **Meal window check dùng `arrival_at_next`** (ước tính thời gian đến POI next), không phải `current_datetime`.

3. **Bearing score** chỉ tính cho POI **giữa**, không tính cho POI đầu và POI cuối.

4. **`is_same_food_type`** ngăn 2 POI liên tiếp cùng loại đồ ăn (e.g., 2 quán Việt Nam liên tiếp).

5. **POI cuối** luôn tính khoảng cách **từ POI đó về user** (ngược lại với POI đầu/giữa).

6. **`first_place_idx`** dùng để tạo **diversity** khi build nhiều routes: route 1 bắt đầu từ POI_0, route 2 từ POI_1, v.v.

---

**Last Updated:** March 4, 2026  
**Author:** Kyanon Team
