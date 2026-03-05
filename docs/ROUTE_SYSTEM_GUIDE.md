## 🎯 Tổng Quan Hệ Thống

### Workflow Tổng Quát
```
2. Hệ thống xử lý:
   ├─ Tìm POI gần user (PostGIS)
   ├─ Tìm POI phù hợp nhu cầu (Qdrant)
   ├─ Lọc POI đang mở cửa (nếu có current_time)
   ├─ Chèn Restaurant (12:00–15:00 / 18:30–22:00)
   │   └─ CHỈ kích hoạt khi user KHÔNG chọn Food & Local Flavours
   ├─ Cafe Counter: Tự động chèn Cafe sau mỗi 2 POI chính
   │   └─ CHỈ kích hoạt khi user KHÔNG chọn Food & Local Flavours
```

---

## 🔍 Logic Xử Lý Query

### Danh Sách 6 Interest Hỗ Trợ (Chọn Tối Đa 3)

| # | Interest | Sub-categories trong pool | Mô tả |
|---|----------|--------------------------|-------|
| 1 | **Food & Local Flavours** | `Cafe & Bakery` + `Restaurant` | Ẩm thực, quán cà phê, nhà hàng |
| 2 | **Culture & Heritage** | `Culture & heritage` | Bảo tàng, di tích, đình chùa, phố cổ |
| 3 | **Nature & Scenery** | `Nature & View` | Công viên, hồ, núi, điểm ngắm cảnh |
| 4 | **Adventure & Leisure** | `Adventure & Leisure` | Hoạt động ngoài trời, thể thao, vui chơi |
| 5 | **Lifestyle & Urban Vibes** | `Lifestyle & Urban Vibes` | Mua sắm, trung tâm thương mại, giải trí đô thị |
| 6 | **Nightlife & Entertainment** | `Nightlife & Entertainment` | Bar, club, phố đêm |

---

### Quy Tắc Cốt Lõi

#### ✅ Quy Tắc 1: Food & Local Flavours → KHÔNG có Meal-Time Insertion

Khi user chọn **Food & Local Flavours**, pool đã có sẵn `Cafe & Bakery` và `Restaurant`.
User có thể ghé ăn bất kỳ lúc nào theo alternation tự nhiên → **Không cần chèn thêm meal-time**.

```
CÓ Food & Local Flavours → meal_time_insertion = FALSE
   Cafe & Bakery và Restaurant xen kẽ đều theo alternation
   Không có ràng buộc khung giờ ăn
```

#### ✅ Quy Tắc 2: Không có Food & Local Flavours → CÓ Meal-Time Insertion

Khi user **không chọn Food**, hệ thống tự động chèn Restaurant vào đúng khung giờ ăn:

```
Lunch window:  12:00 – 15:00
Dinner window: 18:30 – 22:00
```

#### ✅ Quy Tắc 3: Cafe-Counter — Chèn Cafe Sau Mỗi 2 POI Chính

Cafe được chèn tự động sau mỗi **2 POI không phải Cafe và không phải Restaurant**.
Gặp Restaurant (meal-time) → **reset counter về 0**.

```
cafe_counter = 0

Mỗi POI không phải Cafe và không phải Restaurant:  cafe_counter += 1
Khi cafe_counter >= 2:                              → chèn Cafe, reset cafe_counter = 0
Khi gặp Restaurant (meal-time):                    → reset cafe_counter = 0
```

**Ví dụ minh họa (Culture & Heritage + current_time):**
```
POI 1: Culture        → cafe_counter = 1
POI 2: Restaurant     ← LUNCH (meal-time) → cafe_counter = 0  (RESET)
POI 3: Culture        → cafe_counter = 1
POI 4: Culture        → cafe_counter = 2  → TRIGGER chèn Cafe
POI 5: Cafe           → cafe_counter = 0  (RESET)
POI 6: Culture        → cafe_counter = 1
POI 7: Culture        → cafe_counter = 2  → TRIGGER chèn Cafe
POI 8: Cafe (cuối)    → cafe_counter = 0 hoặc 1 POI khác vì POI cuối ưu tiên gần user có điểm cao 
```

> **Lưu ý:** Cafe chỉ được chèn khi **không đang trong meal window**. Nếu cafe_counter >= 2 nhưng
> đúng lúc arrival_time rơi vào meal window → ưu tiên chèn Restaurant trước, Cafe chờ sau.

---

### Tổ Hợp Chọn Interest & Kết Quả Mở Rộng

#### Case 1: Chỉ chọn Food & Local Flavours
```
Pool: ["Cafe & Bakery", "Restaurant"]
Meal-time:    ❌ Không có
Cafe-counter: ❌ Không áp dụng (Cafe đã có trong alternation)
Alternation:  Cafe & Bakery → Restaurant → Cafe & Bakery → Restaurant → ...
```

**Ví dụ Route (target_places=5, khởi đầu 09:00):**
```
09:00 - 09:30  [Cafe & Bakery 1] POI_1        ★4.6
09:38 - 10:28  [Restaurant 1]    POI_2        ★4.6
10:36 - 11:01  [Cafe & Bakery 2] POI_3        ★4.4
11:08 - 11:58  [Restaurant 2]    POI_4        ★4.7
12:05 - 12:30  [Cafe & Bakery 3] POI_5        ★4.5
Kết thúc 12:30 | Tổng: ~180 phút ✅
```

---

#### Case 2: Chỉ chọn Culture & Heritage (không có Food)
```
Pool:         ["Culture & heritage"]
Meal-time:    ✅ Có (overlap meal window 60 phút)
Cafe-counter: ✅ Chèn Cafe sau mỗi 2 POI Culture
Alternation:  Culture → Culture → ... (xen Cafe và Restaurant theo quy tắc)
```

**Ví dụ Route (POI=7, khởi đầu 10:00, có current_time):**
```
10:00 - 10:45  [Culture 1]  POI_1              ★4.7  → counter=1
10:53 - 11:28  [Culture 2]  POI_2              ★4.5  → counter=2 → TRIGGER Cafe
11:35 - 12:00  [Cafe]       POI_3              ★4.3  → counter=0 (RESET)
12:07 - 12:57  [Restaurant] POI_4 ← LUNCH      ★4.7  → counter=0 (RESET)
13:06 - 13:36  [Culture 3]  POI_5              ★4.3  → counter=1
13:43 - 14:13  [Culture 4]  POI_6              ★4.6  → counter=2 → TRIGGER Cafe
14:20 - 14:40  [Cafe]       POI_7 (cuối, gần user)      ★4.4  → counter=0
Kết thúc 14:40 | Tổng: ~280 phút ✅

Ghi chú: Cafe được lấy từ pool Cafe ngoài (không nằm trong interest)
         nhưng sẵn có trong khu vực tìm kiếm.
```

---

#### Case 3: Food & Local Flavours + Culture & Heritage (2 interests)
```
Pool:         ["Cafe & Bakery", "Restaurant", "Culture & heritage"]
Meal-time:    ❌ Không có (đã có Food)
Cafe-counter: ❌ Không áp dụng (Cafe & Bakery đã trong alternation)
Alternation:  Cafe & Bakery → Culture → Restaurant → Culture → Cafe & Bakery → ...
```

**Ví dụ Route (target_places=7, khởi đầu 08:00):**
```
08:00 - 08:30  [Cafe & Bakery 1] POI_1          ★4.6
08:38 - 09:23  [Culture 1]        POI_2         ★4.7
09:30 - 10:20  [Restaurant 1]     POI_3         ★4.6
10:28 - 11:13  [Culture 2]        POI_4         ★4.5
11:21 - 11:46  [Cafe & Bakery 2]  POI_5         ★4.4
11:53 - 12:23  [Culture 3]        POI_6         ★4.3
12:30 - 12:55  [Cafe & Bakery 3]  POI_7 (cuối)  ★4.5
Kết thúc 12:55 | Tổng: ~295 phút ✅
```

---

#### Case 4: Culture & Heritage + Nature & Scenery (không có Food, 2 interests)
```
Pool:         ["Culture & heritage", "Nature & View"]
Meal-time:    ✅ Có (overlap meal window ~ 60 phút)
Cafe-counter: ✅ Chèn Cafe sau mỗi 2 POI (Culture hoặc Nature)
Alternation:  Culture → Nature → Culture → Nature → ...
```

**Ví dụ Route (POI=8, khởi đầu 09:00, có current_time):**
```
09:00 - 09:45  [Culture 1] POI_1                 ★4.7  → counter=1
09:53 - 10:33  [Nature 1]  POI_2                 ★4.5  → counter=2 → TRIGGER Cafe
10:41 - 11:01  [Cafe]      POI_3                 ★4.2  → counter=0 (RESET)
11:08 - 11:43  [Culture 2] POI_4                 ★4.5  → counter=1
11:50 - 12:30  [Nature 2]  POI_5                 ★4.2  → counter=2 → TRIGGER Cafe
               Nhưng next arrival ~12:37 → trong meal window → ưu tiên Restaurant
12:37 - 13:27  [Restaurant] POI_6 ← LUNCH        ★4.4  → counter=0 (RESET)
13:35 - 14:05  [Culture 3] POI_7                 ★4.3  → counter=1
14:12 - 14:37  [Nature 3]  POI_8 (cuối)          ★4.5
Kết thúc 14:37 | Tổng: ~327 phút ✅
```

---

#### Case 5: Food & Local Flavours + Culture & Heritage + Nature & Scenery (3 interests)
```
Pool:         ["Cafe & Bakery", "Restaurant", "Culture & heritage", "Nature & View"]
Meal-time:    ❌ Không có (đã có Food)
Cafe-counter: ❌ Không áp dụng
Alternation:  Cafe & Bakery → Culture → Nature → Restaurant → Cafe & Bakery → ...
```

**Ví dụ Route (POI=9, khởi đầu 08:00):**
```
08:00 - 08:30  [Cafe & Bakery 1] POI_1         ★4.6
08:38 - 09:23  [Culture 1]       POI_2         ★4.7
09:31 - 10:11  [Nature 1]        POI_3         ★4.5
10:19 - 11:09  [Restaurant 1]    POI_4         ★4.7
11:17 - 11:42  [Cafe & Bakery 2] POI_5         ★4.3
11:49 - 12:34  [Culture 2]       POI_6         ★4.5
12:42 - 13:22  [Nature 2]        POI_7         ★4.2
13:30 - 14:20  [Restaurant 2]    POI_8         ★4.6
14:28 - 14:53  [Cafe & Bakery 3] POI_9 (cuối)  ★4.4
Kết thúc 14:53 | Tổng: ~413 phút ✅
```

---

#### Case 6: Culture & Heritage + Nature & Scenery + Adventure & Leisure (3 interests, không có Food)
```
Pool:         ["Culture & heritage", "Nature & View", "Adventure & Leisure"]
Meal-time:    ✅ Có (nếu cung cấp current_time và overlap meal window)
Cafe-counter: ✅ Chèn Cafe sau mỗi 2 POI (Culture, Nature, hoặc Adventure)
Alternation:  Culture → Nature → Adventure → Culture → Nature → Adventure → ...
```

**Ví dụ Route (POI=9, khởi đầu 08:30, có current_time):**
```
08:30 - 09:15  [Culture 1]    POI_1        ★4.7  → counter=1
09:23 - 10:03  [Nature 1]     POI_2                        ★4.5  → counter=2 → TRIGGER Cafe
10:11 - 10:31  [Cafe]         POI_3                     ★4.4  → counter=0 (RESET)
10:38 - 11:38  [Adventure 1]  POI_4        ★4.3  → counter=1
11:46 - 12:26  [Culture 2]    POI_5              ★4.5  → counter=2 → TRIGGER Cafe
               Nhưng next arrival ~12:35 → trong meal window → ưu tiên Restaurant trước
12:35 - 13:25  [Restaurant]   POI_6 ← LUNCH              ★4.7  → counter=0 (RESET)
13:33 - 14:13  [Nature 2]     POI_7                ★4.2  → counter=1
14:21 - 15:21  [Adventure 2]  POI_8            ★4.5  → counter=2 → TRIGGER Cafe
15:29 - 15:49  [Cafe]         POI_9 (cuối)          ★4.3  → counter=0
Kết thúc 15:49 | Tổng: ~439 phút ✅
```

---

### Bảng Tóm Tắt Quyết Định Theo Interest

| Tổ Hợp | Meal-Time Insert | Cafe-Counter | Ghi Chú |
|--------|-----------------|-------------|----------|
| Chỉ Food | ❌ | ❌ | Cafe & Restaurant xen kẽ tự nhiên |
| Food + bất kỳ | ❌ | ❌ | Food đảm bảo đủ ẩm thực |
| Không Food, 1 interest | ✅ | ✅ | Cả 2 cơ chế kích hoạt |
| Không Food, 2 interests | ✅ | ✅ | Cả 2 cơ chế kích hoạt |
| Không Food, 3 interests | ✅ | ✅ | Cả 2 cơ chế kích hoạt |

---

## 🎲 Quy Luật Chọn POI (tỉ lệ distance_score, rating_score có thể điều chỉnh)

### 1. POI Đầu Tiên (Starting POI)

**Mục tiêu:** Chọn POI gần user, có rating cao, phù hợp với semantic query ( thể loại phù hợp vơi interest)

**Score Formula:**
```python
combined_score = (
    0.5  * distance_score    +  # 50% - Gần user (ưu tiên hàng đầu)
    0.1  * similarity_score  +  # 10% - Phù hợp nhu cầu (vì các POI lấy ra thể loại đã đúng rồi nên điểm tính ít)
    0.4  * rating_score         # 40% - Rating cao
)
```

**Ví dụ:**
```python
User location: (21.028511, 105.804817)
Query: "Food & Local Flavours"

POI A: Cafe gần user (0.5km), rating 4.0, similarity 0.85
→ distance_score = 0.95 (rất gần)
→ similarity_score = 0.85
→ rating_score = 0.80 (4.0/5)
→ combined = 0.5*0.95 + 0.1*0.85 + 0.4*0.80 = 0.880

POI B: Restaurant xa user (2km), rating 4.8, similarity 0.92
→ distance_score = 0.75
→ similarity_score = 0.92
→ rating_score = 0.96
→ combined = 0.5*0.75 + 0.1*0.92 + 0.4*0.96 = 0.851

→ Chọn POI A (Cafe) — gần user thắng ở vị trí đầu
```

**Lưu ý đặc biệt:**
- Luôn validate opening hours (luôn đảm bảo thời gian đi tới phù hợp với thời gian mở cửa)

---

### 2. POI Giữa (Middle POIs)

**Mục tiêu:** 
- Xen kẽ category (không lặp liên tiếp)
- Hướng về phía user (bearing score)
- Balance giữa similarity và rating

**Score Formula (áp dụng thống nhất cho mọi mức similarity):**
```python
combined_score = (
    0.40 * distance_score    +  # 40% - Không đi quá xa
    0.10 * similarity_score  +  # 10% - Phù hợp nhu cầu
    0.25 * rating_score      +  # 25% - Rating tốt
    0.25 * bearing_score        # 25% - Hướng về user (tạo vòng cung)
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
# Không được chọn 2 POI liên tiếp cùng category
Ví dụ: [Cafe & Bakery, Restaurant, Culture]

✅ Hợp lệ:   Cafe & Bakery → Culture → Restaurant → Culture → Cafe & Bakery
✅ Hợp lệ:   Culture → Culture → Restaurant → Cafe & Bakery → Cafe & Bakery (Vì POI cuối ưu tiên gần và không quan  tâm category)
❌ Không hợp lệ: Cafe & Bakery → Cafe & Bakery → Culture  (lặp Cafe liên tiếp)
```

**Ví dụ chuỗi (Culture, khởi đầu 10:00):**
```
POI 1: Culture    → counter = 1
POI 2: Restaurant ← LUNCH (reset) → counter = 0
POI 3: Culture    → counter = 1
POI 4: Culture    → counter = 2  → CHÈN Cafe
POI 5: Cafe       → counter = 0
POI 6: Culture    → counter = 1
POI 7: Nature     → counter = 2  → CHÈN Cafe
POI 8: Cafe       → counter = 0 (Có thể là category khác vì POI cuối ưu tiên gần nên không quan tâm category)
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
    0.6  * distance_score    +  # 60% - Ưu tiên gần user tuyệt đối
    0.1  * similarity_score  +  # 10% - Vẫn phù hợp nhu cầu
    0.3  * rating_score         # 30% - Rating tốt
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
→ combined = 0.6*0.92 + 0.1*0.75 + 0.3*0.76 = 0.855

POI B: Restaurant, 1.5km từ user, similarity 0.88, rating 4.5
→ distance_score = 0.85
→ similarity_score = 0.88
→ rating_score = 0.90
→ combined = 0.6*0.85 + 0.1*0.88 + 0.3*0.90 = 0.868

→ Chọn POI B (score cao hơn nhờ rating tốt hơn)
```

---

## 💼 Các Trường Hợp Sử Dụng

### Case 1: Chỉ Food & Local Flavours (không có meal-time)
```json
{
  "semantic_query": "Food & Local Flavours",
  "transportation_mode": "WALKING",
  "current_time": "2026-03-05T09:00:00",
  "max_time_minutes": 180
}
```

**Kết quả:**
- Pool: `[Cafe & Bakery, Restaurant]`
- Meal-time: ❌ Không có
- Cafe-counter: ❌ Không áp dụng
- Alternation: `Cafe & Bakery → Restaurant → Cafe & Bakery → ...`

**Route:**
```
09:00 - 09:30  [Cafe & Bakery 1] Cafe Giảng Trứng         ★4.6
09:38 - 10:28  [Restaurant 1]   Bún Chả Hương Liên        ★4.6
10:36 - 11:01  [Cafe & Bakery 2] Cộng Cà Phê              ★4.4
11:08 - 11:58  [Restaurant 2]   Phở Thìn Lò Đúc           ★4.7
12:06 - 12:26  [Cafe & Bakery 3] The Note Coffee ← cuối   ★4.5
Kết thúc 12:26 | Tổng: ~146 phút ✅
```

---

### Case 2: Chỉ Culture & Heritage — Có Meal-Time + Cafe-Counter
```json
{
  "semantic_query": "Culture & Heritage",
  "transportation_mode": "WALKING",
  "current_time": "2026-03-05T10:00:00",
  "max_time_minutes": 360,
}
```

**Kết quả:**
- Pool: `[Culture & heritage]`
- Meal-time: ✅ Lunch window 12:00–15:00 overlap → chèn Restaurant
- Cafe-counter: ✅ Chèn Cafe sau mỗi 2 POI Culture

**Route:**
```
10:00 - 10:45  [Culture 1] Văn Miếu Quốc Tử Giám     ★4.7  → counter=1
10:53 - 11:28  [Culture 2] Bảo Tàng Phụ Nữ VN        ★4.5  → counter=2 → CHÈN Cafe
11:35 - 12:00  [Cafe]      Tranquil Books & Coffee    ★4.3  → counter=0 (RESET)
12:07 - 12:57  [Restaurant] Phở Thìn ← LUNCH         ★4.7  → counter=0 (RESET)
13:06 - 13:36  [Culture 3] Nhà Hỏa Lò                ★4.3  → counter=1
13:43 - 14:33  [Culture 4] Đền Ngọc Sơn              ★4.6  → counter=2 → CHÈN Cafe
14:40 - 15:20  [Cafe]      Cafe Đình ← cuối          ★4.4  → counter=0
Kết thúc 14:40 | Tổng: ~320 phút ✅
```

---

### Case 3: Food & Local Flavours + Culture & Heritage (có Food, không meal-time)
```json
{
  "semantic_query": "Food & Local Flavours, Culture & Heritage",
  "transportation_mode": "WALKING",
  "current_time": "2026-03-05T08:00:00",
  "max_time_minutes": 360
}
```

**Kết quả:**
- Pool: `[Cafe & Bakery, Restaurant, Culture & heritage]`
- Meal-time: ❌ Không có (do có Food)
- Cafe-counter: ❌ Không áp dụng
- Alternation: `Cafe & Bakery → Culture → Restaurant → Culture → Cafe & Bakery → ...`

**Route:**
```
08:00 - 08:30  [Cafe & Bakery 1] Cafe Giang Trứng         ★4.6
08:38 - 09:23  [Culture 1]      Văn Miếu                  ★4.7
09:30 - 10:20  [Restaurant 1]   Bún Chả Hương Liên        ★4.6
10:28 - 11:13  [Culture 2]      Bảo Tàng Lịch Sử          ★4.5
11:21 - 11:46  [Cafe & Bakery 2] Cộng Cà Phê              ★4.4
11:53 - 12:23  [Culture 3]      Nhà Hỏa Lò                ★4.3
12:30 - 12:55  [Cafe & Bakery 3] The Note Coffee ← cuối   ★4.5
Kết thúc 12:55 | Tổng: ~295 phút ✅
```

---

### Case 4: Culture & Heritage + Nature & Scenery (không Food, có meal-time + cafe-counter)
```json
{
  "semantic_query": "Culture & Heritage, Nature & Scenery",
  "transportation_mode": "WALKING",
  "current_time": "2026-03-05T09:00:00",
  "max_time_minutes": 360
}
```

**Kết quả:**
- Pool: `[Culture & heritage, Nature & View]`
- Meal-time: ✅ Lunch 12:00–15:00 overlap
- Cafe-counter: ✅ Chèn Cafe sau mỗi 2 POI
- Alternation: `Culture → Nature → Culture → Nature → ...`

**Route:**
```
09:00 - 09:45  [Culture 1] Văn Miếu                   ★4.7  → counter=1
09:53 - 10:33  [Nature 1]  Hồ Tây                      ★4.5  → counter=2 → CHÈN Cafe
10:41 - 11:01  [Cafe]      Loading T                   ★4.2  → counter=0 (RESET)
11:08 - 11:43  [Culture 2] Bảo Tàng Phụ Nữ            ★4.5  → counter=1
11:50 - 12:30  [Nature 2]  Vườn Bách Thảo              ★4.2  → counter=2 → TRIGGER Cafe
               Nhưng next arrival ~12:37 → trong meal window → ưu tiên Restaurant
12:37 - 13:27  [Restaurant] Bún Bò Nam Bộ ← LUNCH     ★4.4  → counter=0 (RESET)
13:35 - 14:05  [Culture 3] Nhà Hỏa Lò                 ★4.3  → counter=1
14:12 - 14:37  [Nature 3]  Hồ Hoàn Kiếm ← cuối        ★4.8
Kết thúc 14:37 | Tổng: ~337 phút ✅
```

---

### Case 5: 3 Interests — Food + Culture + Nature (không meal-time)
```json
{
  "semantic_query": "Food & Local Flavours, Culture & Heritage, Nature & Scenery",
  "transportation_mode": "WALKING",
  "current_time": "2026-03-05T08:00:00",
  "max_time_minutes": 540,
  "target_places": 9
}
```

**Kết quả:**
- Pool: `[Cafe & Bakery, Restaurant, Culture & heritage, Nature & View]`
- Meal-time: ❌ Không có (có Food)
- Cafe-counter: ❌ Không áp dụng

**Route:**
```
08:00 - 08:30  [Cafe & Bakery 1] Cafe Giang Trứng         ★4.6
08:38 - 09:23  [Culture 1]      Văn Miếu                  ★4.7
09:31 - 10:11  [Nature 1]       Hồ Tây                    ★4.5
10:19 - 11:09  [Restaurant 1]   Phở Thìn                  ★4.7
11:17 - 11:42  [Cafe & Bakery 2] Tranquil Books            ★4.3
11:49 - 12:34  [Culture 2]      Bảo Tàng Lịch Sử          ★4.5
12:42 - 13:22  [Nature 2]       Vườn Bách Thảo             ★4.2
13:30 - 14:20  [Restaurant 2]   Bún Chả Hương Liên        ★4.6
14:28 - 14:53  [Cafe & Bakery 3] Cộng Cà Phê ← cuối       ★4.4
Kết thúc 14:53 | Tổng: ~413 phút ✅
```

---

### Case 6: 3 Interests — Culture + Nature + Adventure (không Food, có meal-time + cafe-counter)
```json
{
  "semantic_query": "Culture & Heritage, Nature & Scenery, Adventure & Leisure",
  "transportation_mode": "WALKING",
  "current_time": "2026-03-05T08:30:00",
  "max_time_minutes": 480,
  "target_places": 9
}
```

**Kết quả:**
- Pool: `[Culture & heritage, Nature & View, Adventure & Leisure]`
- Meal-time: ✅ Lunch 12:00–15:00 overlap
- Cafe-counter: ✅ Chèn Cafe sau mỗi 2 POI

**Route:**
```
08:30 - 09:15  [Culture 1]    Văn Miếu                   ★4.7  → counter=1
09:23 - 10:03  [Nature 1]     Hồ Tây                     ★4.5  → counter=2 → CHÈN Cafe
10:11 - 10:31  [Cafe]         Cafe Đình                  ★4.4  → counter=0 (RESET)
10:38 - 11:38  [Adventure 1]  Paddle Boarding Hồ Tây     ★4.3  → counter=1
11:46 - 12:26  [Culture 2]    Bảo Tàng Lịch Sử           ★4.5  → counter=2 → TRIGGER Cafe
               next arrival ~12:35 → trong meal window → ưu tiên Restaurant trước
12:35 - 13:25  [Restaurant]   Phở Thìn ← LUNCH           ★4.7  → counter=0 (RESET)
13:33 - 14:13  [Nature 2]     Vườn Bách Thảo              ★4.2  → counter=1
14:21 - 15:21  [Adventure 2]  Escape Game Hà Nội         ★4.5  → counter=2 → CHÈN Cafe
15:29 - 15:49  [Cafe]         Tranquil Books ← cuối       ★4.3  → counter=0
Kết thúc 15:49 | Tổng: ~439 phút ✅
```

## 📞 Support & Contact

Nếu có thắc mắc về API, vui lòng liên hệ team phát triển.

---

**Last Updated:** March 5, 2026
