# 🎯 Demo Bearing - Hướng dẫn sử dụng đầy đủ

## 📂 Files trong folder

```
Demo_Bearing/
├── visualization.html                    # Version cơ bản
├── interactive_demo.html                 # Demo với scenarios có sẵn
├── visualization_advanced.html           # Version gốc với analyze mode
├── visualization_advanced_fixed.html     # ✅ VERSION MỚI NHẤT (dùng file này!)
├── route_algorithm.py                    # Python backend (optional)
├── requirements.txt                      # Python dependencies
├── patch_visualization.py                # Script để patch HTML
├── README.md                             # Hướng dẫn cơ bản
└── SETUP_GUIDE.md                        # Hướng dẫn chi tiết
```

## 🚀 Cách sử dụng

### Cách 1: Mở trực tiếp (Recommended)

```bash
open visualization_advanced_fixed.html
```

### Cách 2: Với Python Backend (Advanced)

```bash
# 1. Install dependencies
pip install flask flask-cors

# 2. Start backend
python route_algorithm.py

# 3. Mở HTML
open visualization_advanced_fixed.html
```

## ✨ Các cải tiến mới

### 1. **Fix mô tả góc Bearing** ✅

**Trước (sai):**
- "Bearing từ User đến POI" (không rõ là góc nào)

**Sau (đúng):**
```
🧭 Giải thích Bearing:
Vector 1: POI #1 → POI #2
Vector 2: POI #2 → POI #3  
Góc Δ: Chênh lệch giữa 2 vector
Bearing Score: 1 - (Δ / 180°) = 0.xxx
```

**Ví dụ cụ thể:**
- User ở (21.0285, 105.8542)
- POI #1: Restaurant (bearing 45° từ User)
- POI #2: Cafe (bearing 60° từ POI #1)
- **Góc Δ = |60° - 45°| = 15°**
- **Bearing score = 1 - (15/180) = 0.917**

### 2. **Thêm Distance Matrix** ✅

Hiển thị bảng khoảng cách giữa tất cả POIs:

```
📐 Distance Matrix (Route POIs):

        USER   POI#1  POI#2  POI#3
USER     0    500m   800m   1200m
POI#1  500m    0    350m    700m
POI#2  800m  350m     0     400m
POI#3  1200m  700m  400m      0
```

**Công thức:**
```javascript
distance[i][j] = haversine(lat[i], lon[i], lat[j], lon[j])
```

### 3. **Bearing Normalization** ✅

**Vấn đề:** Góc 350° và 10° thực ra chỉ chênh nhau 20°, không phải 340°

**Giải pháp:**
```python
bearing_diff = |bearing1 - bearing2|
if bearing_diff > 180:
    bearing_diff = 360 - bearing_diff  # Normalize

bearing_score = 1.0 - (bearing_diff / 180.0)
```

**Ví dụ:**
- Vector 1 hướng 350° (gần Bắc, lệch Tây)
- Vector 2 hướng 10° (gần Bắc, lệch Đông)
- Diff = |350 - 10| = 340° ❌ (SAI!)
- Normalize: 360 - 340 = 20° ✅ (ĐÚNG!)
- Score = 1 - (20/180) = 0.889

## 🎮 Hướng dẫn sử dụng UI

### Bước 1: Tạo Scenario
1. Điều chỉnh **Bán kính** (500-5000m)
2. Chọn **Phương tiện** (Đi bộ / Xe đạp / Ô tô / Xe máy)
3. Đặt **Số POI** candidates (5-30)
4. Click **"🔄 Tạo kịch bản mới"**

### Bước 2: Build Route
1. Đặt **Số POI trong route** (3-10)
2. Click **"🛣️ Xây dựng Route"**
3. Quan sát route với góc bearing

### Bước 3: Route Mode (🗺️)
- Xem route hoàn chỉnh
- Góc bearing hiển thị trên mỗi đoạn
- Format: `45°` ở giữa mỗi mũi tên

### Bước 4: Analyze Mode (🔍)
1. Click nút **"🔍 Analyze"**
2. Click vào **bất kỳ POI nào** trong route (điểm đỏ)
3. Xem phân tích chi tiết bên phải:
   - ✅ Công thức tính score
   - ✅ Giải thích bearing với 2 vectors
   - ✅ Distance matrix
   - ✅ Bảng so sánh POI candidates
   - ✅ Lý do chọn POI này

### Bước 5: Quay lại
- Click **"🗺️ Route"** để xem lại route ban đầu

## 📊 Phân tích Bearing trong Analyze Mode

### Hiển thị trên Map:

1. **Bearing lines** (đường chấm):
   - Màu xanh lá đậm: Từ current POI → selected POI
   - Màu đỏ nhạt: Từ current POI → các POI khác trong route
   - Màu xanh nhạt: Từ current POI → POI candidates

2. **Bearing arc** (cung tròn tím):
   - Vẽ góc Δ giữa vector trước và vector hiện tại
   - Hiển thị số `Δ110°` ở trên arc

3. **POI highlight**:
   - Xanh lá lớn: POI đang phân tích
   - Đỏ: POI khác trong route
   - Xanh dương: POI candidates

### Hiển thị trên Panel:

```
🧭 Giải thích Bearing:
Vector 1: POI #1 → POI #2
Vector 2: POI #2 → POI #3
Góc Δ: Chênh lệch giữa 2 vector
Bearing Score: 1 - (Δ / 180°) = 0.750
• 0° (cùng hướng) = 1.0 (tốt nhất)
• 180° (ngược hướng) = 0.0 (tệ nhất)
```

## 🧮 Chi tiết thuật toán

### Combined Score Formula

**POI đầu tiên:**
```
score = 0.1 × distance + 0.45 × similarity + 0.45 × rating
```
- Ưu tiên similarity và rating
- Distance ít quan trọng

**POI giữa (High similarity ≥ 0.8):**
```
score = 0.15 × distance + 0.5 × similarity + 0.3 × rating + 0.05 × bearing
```
- Ưu tiên similarity (phù hợp query)
- Bearing có trọng số nhỏ

**POI giữa (Low similarity < 0.8):**
```
score = 0.25 × distance + 0.1 × similarity + 0.4 × rating + 0.25 × bearing
```
- Ưu tiên rating (chất lượng POI)
- Bearing quan trọng hơn để tránh zíc zắc

**POI cuối:**
```
score = 0.4 × distance + 0.3 × similarity + 0.3 × rating
```
- Ưu tiên gần User để giảm thời gian về

### Distance Score Normalization

```javascript
distance_score = 1 - (actual_distance / max_radius)
```
- 0m → score = 1.0 (gần nhất, tốt nhất)
- max_radius → score = 0.0 (xa nhất, tệ nhất)

**Ví dụ:**
- Max radius = 2000m
- Actual distance = 500m
- Score = 1 - (500/2000) = 0.75

## 🔧 Python Backend (Optional)

### Tại sao cần Backend?

1. **Maintainability**: Logic tách riêng, dễ test
2. **Performance**: Python nhanh hơn JS cho tính toán phức tạp
3. **Reusability**: Có thể dùng cho mobile app, API, etc.

### API Endpoints

#### POST /api/build_route

Xây dựng route từ POI candidates:

```bash
curl -X POST http://localhost:5000/api/build_route \
  -H "Content-Type: application/json" \
  -d '{
    "pois": [...],
    "user_location": {"lat": 21.0285, "lon": 105.8542},
    "target_count": 5,
    "max_radius": 2000
  }'
```

#### POST /api/calculate_distance_matrix

Tính distance matrix:

```bash
curl -X POST http://localhost:5000/api/calculate_distance_matrix \
  -H "Content-Type: application/json" \
  -d '{
    "user_location": {"lat": 21.0285, "lon": 105.8542},
    "pois": [...]
  }'
```

### Testing Backend

```python
# Test bearing calculation
from route_algorithm import GeographicUtils

geo = GeographicUtils()

# North (0°)
print(geo.calculate_bearing(21.0, 105.0, 22.0, 105.0))  # ~0°

# East (90°)
print(geo.calculate_bearing(21.0, 105.0, 21.0, 106.0))  # ~90°

# Bearing difference normalization
print(geo.calculate_bearing_difference(350, 10))  # 20°, not 340°!
```

## 🐛 Troubleshooting

### Distance matrix không hiển thị

**Check:**
```javascript
// Trong browser console
console.log('Route:', route);
console.log('Distance Matrix:', buildDistanceMatrix());
```

### Bearing góc bị sai

**Kiểm tra:**
- Vector 1 phải là hướng đi **TRƯỚC ĐÓ**
- Vector 2 là hướng đi **TIẾP THEO**
- Normalize góc > 180° bằng `360 - diff`

### POI không clickable trong Analyze Mode

**Fix:**
- Chắc chắn đang ở **Analyze Mode** (nút 🔍 active)
- POI phải nằm **trong route** (màu đỏ)
- Click đúng vào điểm tròn POI

## 📚 Tài liệu tham khảo

- [Haversine Formula](https://en.wikipedia.org/wiki/Haversine_formula) - Tính khoảng cách
- [Bearing Calculation](https://www.movable-type.co.uk/scripts/latlong.html) - Tính góc bearing
- [Greedy Algorithm](https://en.wikipedia.org/wiki/Greedy_algorithm) - Route building

## 📝 Change Log

### v3.0 (Latest) - visualization_advanced_fixed.html
- ✅ Fix mô tả bearing (giải thích rõ vector 1 vs vector 2)
- ✅ Thêm distance matrix display
- ✅ Thêm bearing normalization explanation
- ✅ Cải thiện UI trong analyze mode

### v2.0 - visualization_advanced.html
- Thêm analyze mode
- Click POI để xem chi tiết
- Bearing lines và arc

### v1.0 - visualization.html
- Route mode cơ bản
- Generate random POIs

## 💡 Tips

1. **Test bearing optimization:**
   - Tạo route với nhiều POIs (10+)
   - Chuyển sang Analyze Mode
   - Click từng POI để xem bearing score
   - POI có bearing score cao = đi thẳng, ít zíc zắc

2. **Hiểu distance matrix:**
   - Diagonal = 0 (khoảng cách tới chính nó)
   - Matrix đối xứng: `dist[i][j] = dist[j][i]`
   - Dùng để optimize route ordering

3. **Debug bearing:**
   - Quan sát arc tím trong Analyze Mode
   - Góc Δ nhỏ (< 45°) = đi khá thẳng
   - Góc Δ lớn (> 90°) = route zíc zắc, cần optimize

---

Made with ❤️ by Kyanon Team - 2026
