# 🗺️ Route Algorithm Visualization

Visualization tool để minh họa thuật toán tìm kiếm và xây dựng route trong `radius_logic`

## � Quick Start

### Option 1: Standalone (No Backend Required)
```bash
open visualization_advanced.html
```

### Option 2: With Python Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Start backend server
python route_algorithm.py

# Open browser
open visualization_advanced.html
```

## �📋 Mô tả

Tool này mô phỏng trực quan các bước trong thuật toán:

### 1. **H3 Radius Search** (`h3_radius_search.py`)
- Vẽ vòng tròn bán kính tìm kiếm (màu xám)
- Tâm là vị trí User (điểm xanh lá)
- Hiển thị các POI candidates trong vòng tròn (điểm xanh dương)

### 2. **Bearing Calculation** (`geographic_utils.py`)
- **Bearing**: Góc giữa hướng Bắc và vector nối 2 điểm (0-360°)
- **Bearing Difference**: Góc giữa 2 vectors liên tiếp trong route
  - Vector 1: Từ POI trước → POI hiện tại
  - Vector 2: Từ POI hiện tại → POI tiếp theo
  - Δ = |bearing2 - bearing1| (chuẩn hóa 0-180°)
- Vẽ các đường thẳng chấm từ User đến POI (bearing lines)
- Hiển thị hướng Bắc-Nam-Đông-Tây để tham chiếu
- Hiển thị góc Δ bằng arc màu tím trong Analyze Mode

### 3. **Route Building** (`route_builder_*.py`, `calculator.py`)
- Chọn POI theo combined score:
  - **POI đầu**: `0.1×distance + 0.45×similarity + 0.45×rating`
  - **POI giữa**: thêm `bearing_score` để tránh zíc zắc
    - High similarity: `0.15×distance + 0.5×similarity + 0.3×rating + 0.05×bearing`
    - Low similarity: `0.25×distance + 0.1×similarity + 0.4×rating + 0.25×bearing`
  - **POI cuối**: ưu tiên gần User `0.4×distance + 0.3×similarity + 0.3×rating`
- Vẽ route path (mũi tên màu đỏ)
- Route quay về User location

### 4. **Bearing Optimization**
- `bearing_score = 1.0 - (bearing_diff / 180.0)`
- 0° (cùng hướng) → score = 1.0
- 180° (ngược hướng) → score = 0.0
- Giúp route đi theo hướng thẳng, giảm quãng đường

## 🚀 Cách sử dụng

### Mở file HTML
```bash
# Option 1: Mở trực tiếp bằng browser
open Demo_Bearing/visualization.html

# Option 2: Sử dụng Python HTTP server
cd Demo_Bearing
python3 -m http.server 8000
# Truy cập: http://localhost:8000/visualization.html
```

### Tương tác với UI

#### Controls (Bảng điều khiển bên trái)

1. **🌍 Bán kính tìm kiếm**: Điều chỉnh search radius (500m - 5000m)
   - Tương ứng với H3 k-ring trong config

2. **🚶 Phương tiện di chuyển**: Chọn transportation mode
   - Đi bộ / Xe đạp / Ô tô / Xe máy
   - Ảnh hưởng đến k-ring value

3. **📍 Số lượng POI**: Số POI candidates được generate (5-30)

4. **🎯 Số POI trong route**: Target số POI trong route cuối cùng (3-10)

#### Buttons

- **🔄 Tạo kịch bản mới**: Generate random POIs xung quanh User
- **🛣️ Xây dựng Route**: Chạy thuật toán greedy để build route
- **🗑️ Xóa Route**: Clear route hiện tại, giữ POI candidates

#### Statistics

- **POI tìm được**: Số POI trong search radius
- **POI trong route**: Số POI được chọn vào route

#### Danh sách POI

Hiển thị chi tiết các POI trong route:
- Tên POI
- Khoảng cách từ User (km)
- Góc bearing (độ)

## 🎨 Chú giải màu sắc

| Màu | Ý nghĩa |
|-----|---------|
| 🟢 Xanh lá (USER) | Vị trí User - tâm của vòng tròn |
| 🔵 Xanh dương | POI candidates (trong search radius) |
| 🔴 Đỏ | POI được chọn vào route |
| ⚪ Xám nhạt | Vòng tròn search radius |
| 🔵 Xanh chấm | Bearing lines (User → POI) |
| 🔴 Đỏ mũi tên | Route path (thứ tự di chuyển) |

## 🔧 Thuật toán chi tiết

### Greedy Route Building Algorithm

```python
1. Khởi tạo:
   - current_pos = User location
   - route = []
   - used = set()
   - prev_bearing = None

2. For step in range(target_count):
   a. is_first = (step == 0)
   b. is_last = (step == target_count - 1)
   
   c. Tìm POI chưa dùng có combined_score cao nhất:
      - Tính distance từ current_pos đến POI
      - Tính bearing từ current_pos đến POI
      - Tính bearing_diff với prev_bearing
      - Calculate combined_score với weights tương ứng
   
   d. Thêm best_POI vào route
   e. Update: current_pos = best_POI
   f. Update: prev_bearing = bearing(current_pos → best_POI)

3. Return route
```

### Combined Score Weights

#### POI đầu tiên (is_first = True)
```
combined = 0.1 × distance_score + 0.45 × similarity + 0.45 × rating
```
- Ưu tiên POI có similarity và rating cao
- Distance ít quan trọng

#### POI giữa (is_first = False, is_last = False)

**High similarity (≥ 0.8)**:
```
combined = 0.15 × distance_score + 0.5 × similarity + 0.3 × rating + 0.05 × bearing_score
```
- Ưu tiên similarity (relevant với query)
- Bearing ít quan trọng

**Low similarity (< 0.8)**:
```
combined = 0.25 × distance_score + 0.1 × similarity + 0.4 × rating + 0.25 × bearing_score
```
- Ưu tiên rating (chất lượng POI)
- Bearing quan trọng hơn để tránh zíc zắc

#### POI cuối cùng (is_last = True)
```
combined = 0.4 × distance_score + 0.3 × similarity + 0.3 × rating
```
- Ưu tiên POI gần User để giảm thời gian về
- Distance quan trọng nhất

### Bearing Score Calculation

```python
bearing_diff = |bearing1 - bearing2|
if bearing_diff > 180:
    bearing_diff = 360 - bearing_diff

bearing_score = 1.0 - (bearing_diff / 180.0)
```

- `0°`: Cùng hướng → `score = 1.0` (tốt nhất)
- `90°`: Vuông góc → `score = 0.5` (trung bình)
- `180°`: Ngược hướng → `score = 0.0` (tệ nhất)

## 📊 Ví dụ kịch bản

### Scenario 1: Short Walking Tour
```
- Bán kính: 1000m
- Phương tiện: Đi bộ
- POI candidates: 10
- Target POIs: 4
→ Route ngắn, gọn, ít zíc zắc
```

### Scenario 2: Motorbike Day Trip
```
- Bán kính: 3000m
- Phương tiện: Xe máy
- POI candidates: 20
- Target POIs: 8
→ Route dài, nhiều điểm tham quan
```

## 🔗 Liên kết với code

| File visualization | File code tương ứng |
|-------------------|---------------------|
| `calculateDistance()` | `geographic_utils.py::calculate_distance_haversine()` |
| `calculateBearing()` | `geographic_utils.py::calculate_bearing()` |
| `calculateBearingDifference()` | `geographic_utils.py::calculate_bearing_difference()` |
| `calculateCombinedScore()` | `calculator.py::calculate_combined_score()` |
| `buildRouteAlgorithm()` | `route_builder_base.py`, `route_builder_target.py` |

## 💡 Tips

1. **Test bearing optimization**: 
   - Tạo route với POI count cao (20+)
   - Xem route có đi thẳng hay quanh co
   - Adjust target POIs để thấy sự khác biệt

2. **Compare transportation modes**:
   - Đổi phương tiện → search radius thay đổi
   - Walking: radius nhỏ, POI gần
   - Motorbike: radius lớn, POI xa

3. **Visualize bearing impact**:
   - Quan sát bearing lines (đường chấm)
   - Route path (đường đỏ) cố gắng đi theo hướng thẳng
   - POI cuối thường gần User (giảm thời gian về)

## 📝 TODO

- [ ] Thêm animation cho route building process
- [ ] Hiển thị combined score trên mỗi POI
- [ ] Export route data to JSON
- [ ] Import real POI data từ database
- [ ] Hỗ trợ meal-time Restaurant insertion
- [ ] Visualize H3 hexagon cells

## 📄 License

MIT License - Kyanon Team 2026
