# Cơ Chế Bearing Filter - Tạo Vòng Cung Về User

## Tổng Quan

**Bearing Filter** là cơ chế lọc POI theo góc địa lý, chỉ giữ lại các POI nằm trong phạm vi góc cho phép, giúp tuyến đường có dạng **vòng cung tiến dần về phía user** thay vì đi lung tung hoặc quay ngược lại.

### Ưu Điểm

- ✅ **Loại bỏ hard** các POI nằm phía sau (180° sau lưng)
- ✅ **Tạo vòng cung tự nhiên** về phía user location
- ✅ **Giảm đường đi zíc zắc** và quay ngược
- ✅ **Mở rộng dần** nếu không tìm được POI trong phạm vi ban đầu
- ✅ **Vẫn giữ bearing_score** để rank các POI đã qua lọc

---

## 1. Cơ Chế Hoạt Động

### 1.1. Xác Định Target Bearing

Với mỗi POI giữa, tính **target_bearing** = hướng từ vị trí hiện tại về **user location**.

```python
# Vị trí hiện tại
if current_pos == 0:  # Từ user
    current_lat, current_lon = user_location
else:
    current_lat, current_lon = places[current_pos - 1]["lat"], places[current_pos - 1]["lon"]

# Hướng về user (target)
target_bearing = calculate_bearing(current_lat, current_lon, user_location[0], user_location[1])
```

**Ví dụ:**
- User tại: (21.0285, 105.8542) - Hồ Gươm
- POI hiện tại: (21.0227, 105.8363) - Văn Miếu
- Target bearing = 85° (hướng Đông - về phía user)

### 1.2. Lọc POI Theo Góc

Chỉ giữ lại POI nằm trong phạm vi **±bearing_range** quanh target_bearing.

```python
bearing_range = 90°  # ±90° ban đầu (nửa vòng tròn phía trước)

for candidate_poi in places:
    # Tính hướng từ vị trí hiện tại đến POI candidate
    poi_bearing = calculate_bearing(current_lat, current_lon, candidate_poi.lat, candidate_poi.lon)
    
    # Tính góc chênh lệch
    bearing_diff = calculate_bearing_difference(target_bearing, poi_bearing)
    
    # Chỉ giữ POI trong phạm vi
    if bearing_diff <= bearing_range:
        candidates.append(candidate_poi)  # ✅ Pass filter
    else:
        continue  # ❌ Loại bỏ
```

**Hình Minh Họa:**

```
                    User Location
                         ⭐
                        /|\
                       / | \
                      /  |  \
          ±90° →     /   |   \    ← ±90°
                    /    |    \
                   /     |     \
                  /  ✅  |  ✅  \    ← Chấp nhận POI trong ±90°
                 /       |       \
        --------●--------+--------●-------
         ❌ Loại  Current   Loại ❌
                   Pos
```

### 1.3. Mở Rộng Dần Nếu Không Tìm Được

Nếu không có POI nào trong phạm vi ±90°, tự động mở rộng:

- **±90°** (ban đầu - nửa vòng tròn phía trước)
- → **±105°** (mở rộng +15°)
- → **±120°** (mở rộng +15°)
- → **±135°** (mở rộng +15°)
- → ... đến **±180°** (tối đa - toàn bộ vòng tròn)

```python
bearing_range = RouteConfig.INITIAL_BEARING_RANGE  # 90°

while not candidates and bearing_range <= RouteConfig.MAX_BEARING_RANGE:
    # Lọc POI với bearing_range hiện tại
    candidates = filter_pois_by_bearing(target_bearing, bearing_range)
    
    # Nếu không tìm được, mở rộng thêm
    if not candidates and bearing_range < RouteConfig.MAX_BEARING_RANGE:
        bearing_range += RouteConfig.BEARING_EXPANSION_STEP  # +15°
        print(f"⚠️ Mở rộng sang ±{bearing_range}°")
    else:
        break
```

---

## 2. Cấu Hình Trong `route_config.py`

```python
# Bearing filter configuration
INITIAL_BEARING_RANGE = 90.0      # ±90° ban đầu
BEARING_EXPANSION_STEP = 15.0     # Mở rộng +15° mỗi lần
MAX_BEARING_RANGE = 180.0         # Tối đa ±180° (toàn bộ)
```

### Tùy Chỉnh

- **INITIAL_BEARING_RANGE**: Giảm xuống 60° nếu muốn tuyến đường thẳng hơn (ít rẽ ngoặt)
- **BEARING_EXPANSION_STEP**: Tăng lên 30° nếu muốn mở rộng nhanh hơn
- **MAX_BEARING_RANGE**: Giữ 180° để đảm bảo luôn tìm được POI

---

## 3. Áp Dụng Cho POI Nào?

### ✅ POI Giữa (Middle POIs)

Bearing filter **CHỈ** áp dụng cho **POI giữa** (không áp dụng cho POI đầu và POI cuối).

**Lý do:**
- **POI đầu**: Chọn dựa trên combined_score cao nhất (distance + similarity + rating)
- **POI giữa**: Cần tạo vòng cung → áp dụng bearing filter
- **POI cuối**: Chọn gần user nhất để giảm thời gian quay về

---

## 4. Kết Hợp Với Bearing Score

Sau khi lọc POI theo bearing filter, **vẫn tính bearing_score** để rank các POI:

```python
# Sau khi lọc bearing filter → candidates = [POI_1, POI_2, POI_3, ...]

for candidate in candidates:
    # Tính combined_score (bao gồm bearing_score)
    combined_score = calculate_combined_score(
        ...,
        prev_bearing=prev_bearing,  # Hướng đoạn vừa đi
        user_location=user_location
    )
    
    # bearing_score = 1 - (angle_diff / 180)
    # Góc chênh nhỏ (cùng hướng) → score cao
```

**Ví dụ:**

Giả sử có 3 POI qua filter:
- POI A: bearing_diff = 5°  → bearing_score = 1 - (5/180) = 0.972 ✅ **Cao nhất**
- POI B: bearing_diff = 30° → bearing_score = 1 - (30/180) = 0.833
- POI C: bearing_diff = 60° → bearing_score = 1 - (60/180) = 0.667

Combined score của POI A sẽ cao hơn nhờ bearing_score.

---

## 5. Workflow Chọn POI Giữa

```
┌─────────────────────────────────────────────┐
│ 1. Tính target_bearing về user             │
│    target_bearing = 85° (Đông)             │
└───────────────┬─────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────┐
│ 2. Bắt đầu với bearing_range = ±90°        │
└───────────────┬─────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────┐
│ 3. Lọc POI theo bearing filter              │
│    ✅ Giữ POI trong ±90° quanh target       │
│    ❌ Loại POI ngoài phạm vi                │
└───────────────┬─────────────────────────────┘
                │
                ▼
        ┌───────┴───────┐
        │ Tìm được POI? │
        └───────┬───────┘
                │
        ┌───────┴───────┐
        │ YES           │ NO
        ▼               ▼
┌──────────────┐  ┌──────────────────────┐
│ 4. Tính     │  │ Mở rộng +15°         │
│ combined    │  │ bearing_range = 105° │
│ score       │  └──────┬───────────────┘
└──────┬──────┘         │
       │                └──────► Back to Step 3
       ▼
┌──────────────────────────────┐
│ 5. Chọn POI score cao nhất   │
└──────────────────────────────┘
```

---

## 6. Ví Dụ Thực Tế

### Scenario: Tạo route 5 POI tại Hà Nội

**Input:**
- User location: Hồ Gươm (21.0285, 105.8542)
- Target: 5 POI (1 đầu + 3 giữa + 1 cuối)

**Bước 1: Chọn POI đầu**
- POI 1: Văn Miếu (21.0277, 105.8363)
- Không áp dụng bearing filter

**Bước 2: Chọn POI giữa #1**
- Current pos: Văn Miếu
- Target bearing về user: 85° (Đông)
- Bearing range: ±90° (chấp nhận 0-175°, loại 175-360°)
- Candidates:
  - POI A (Chùa Một Cột): bearing = 82° → ✅ Pass (diff = 3°)
  - POI B (Hoàng Thành): bearing = 95° → ✅ Pass (diff = 10°)
  - POI C (Cầu Long Biên): bearing = 190° → ❌ Loại (diff = 105° > 90°)
- **Chọn: POI A** (bearing_score cao nhất)

**Bước 3: Chọn POI giữa #2**
- Current pos: Chùa Một Cột
- Target bearing về user: 78° (tiếp tục về phía Đông)
- Bearing range: ±90°
- **Chọn: Hoàng Thành** (bearing = 80°, diff = 2°)

**Bước 4: Chọn POI giữa #3**
- Current pos: Hoàng Thành
- Target bearing về user: 70°
- Bearing range: ±90° → Không tìm được → mở rộng sang ±105° → Tìm được
- **Chọn: Nhà Thờ Lớn** (bearing = 68°, diff = 2°)

**Bước 5: Chọn POI cuối**
- Chọn POI gần user nhất (không áp dụng bearing filter)
- **Chọn: Nhà Hát Lớn** (distance = 0.8km)

**Kết quả:**
- Route: Hồ Gươm → Văn Miếu → Chùa Một Cột → Hoàng Thành → Nhà Thờ Lớn → Nhà Hát Lớn → Hồ Gươm
- Hình dạng: **Vòng cung tiến dần về user** ✅
- Không có đoạn quay ngược 180° ✅

---

## 7. So Sánh Trước/Sau

### ❌ Trước (Chỉ có bearing_score)

```
User ⭐
      \
       \  POI1 ●
        \    /
         \  /   ← Zíc zắc, quay ngược
          \/
          /\
         /  \
    POI2 ●  ● POI3
```

- POI2 nằm phía sau POI1 → quay ngược
- Bearing score thấp nhưng vẫn được chọn nếu similarity cao

### ✅ Sau (Bearing filter + bearing_score)

```
User ⭐
      ↑
      |  ● POI3
      | /
      |/     ← Vòng cung mượt mà
     ● POI2
    /
   /
  ● POI1
```

- POI2, POI3 luôn nằm trong ±90° về phía user
- Tạo vòng cung tự nhiên, không quay ngược

---

## 8. Debug & Monitoring

Khi chạy route builder, sẽ in ra log:

```
🧭 Bearing filter: target=85.0°, range=±90.0°
   ⚠️  Không tìm được POI, mở rộng sang ±105.0°
🧭 Bearing filter: target=85.0°, range=±105.0°
   ✅ Tìm được 3 candidates
   
POI được chọn:
   - Tên: Chùa Một Cột
   - Bearing: 82.0° (diff = 3.0°)
   - Bearing score: 0.983
```

---

## 9. Tham Khảo Code

- **geographic_utils.py**: `is_poi_in_bearing_range()` - Hàm kiểm tra POI trong phạm vi
- **route_config.py**: Cấu hình INITIAL_BEARING_RANGE, BEARING_EXPANSION_STEP, MAX_BEARING_RANGE
- **route_builder_target.py**: `_select_middle_poi()` - Áp dụng bearing filter cho POI giữa
- **route_builder_duration.py**: `_select_middle_poi()` - Áp dụng bearing filter cho POI giữa

---

## 10. FAQ

**Q: Tại sao không áp dụng cho POI đầu và POI cuối?**

A: 
- POI đầu: Cần chọn POI tốt nhất dựa trên similarity + rating, không quan tâm hướng
- POI cuối: Cần gần user để giảm thời gian về, không quan tâm hướng

**Q: Nếu bearing_range = 180° mà vẫn không tìm được POI?**

A: Trường hợp này chỉ xảy ra khi:
- Tất cả POI đã visited
- Hoặc không pass các filter khác (category, opening hours, time budget)

**Q: Có thể tắt bearing filter không?**

A: Có, set `INITIAL_BEARING_RANGE = 180.0` trong `route_config.py` → filter không có tác dụng (chấp nhận tất cả góc).

**Q: Bearing filter có làm tăng thời gian xử lý không?**

A: Không đáng kể. Tính toán bearing rất nhanh (< 1ms), worst case là loop nhiều lần khi mở rộng góc (tối đa 6-7 lần nếu EXPANSION_STEP = 15°).

---

**Author:** Kyanon Team  
**Created:** 2026-01-30  
**Last Updated:** 2026-01-30
