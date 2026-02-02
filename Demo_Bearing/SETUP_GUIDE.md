# Route Algorithm Visualization - Setup Guide

## 📦 Cài đặt

### 1. Install Python dependencies

```bash
cd Demo_Bearing
pip install -r requirements.txt
```

### 2. Start Python Backend Server

```bash
python route_algorithm.py
```

Server sẽ chạy tại: `http://localhost:5000`

### 3. Mở HTML file

Có 2 options:

**Option A: Chạy standalone** (không cần backend)
- Mở trực tiếp file `visualization_advanced.html` trong browser
- Thuật toán chạy JavaScript local

**Option B: Với Python backend** (recommended)
- Start Python server trước (bước 2)
- Mở `visualization_with_backend.html`
- Thuật toán gọi API Python

## 🔧 Các thay đổi chính

### 1. **Fix mô tả góc Bearing**

❌ **Trước:** "Bearing từ User đến POI" (không rõ ràng)

✅ **Sau:** 
```
Vector 1 (trước): POI #(n-1) → POI #n  
Vector 2 (hiện tại): POI #n → POI #(n+1)
Góc Δ: Chênh lệch giữa 2 vector = xxx°
Bearing Score: 1 - (Δ / 180°) = 0.xxx
```

**Ví dụ:**
- Vector 1: USER → POI #1 (bearing = 45°)
- Vector 2: POI #1 → POI #2 (bearing = 60°)
- Góc Δ = |60° - 45°| = 15°
- Bearing score = 1 - (15/180) = 0.917

### 2. **Thêm Distance Matrix**

Hiển thị ma trận khoảng cách giữa tất cả POIs trong route:

```
        USER   POI#1  POI#2  POI#3
USER     0    500m   800m   1200m
POI#1  500m    0    350m    700m
POI#2  800m  350m     0     400m
POI#3  1200m  700m  400m      0
```

**Công thức:** `distance[i][j] = Haversine(coord[i], coord[j])`

### 3. **Bearing Normalization**

**Công thức chuẩn hóa:**
```python
bearing_difference = |bearing1 - bearing2|
if bearing_difference > 180:
    bearing_difference = 360 - bearing_difference

bearing_score = 1.0 - (bearing_difference / 180.0)
```

**Ví dụ:**
- `bearing1 = 350°`, `bearing2 = 10°`
- `diff = |350 - 10| = 340°`
- `diff > 180 → diff = 360 - 340 = 20°` (normalize)
- `score = 1 - (20/180) = 0.889`

## 📊 Giải thích thuật toán

### Distance Matrix Building

```python
def build_distance_matrix(user_location, pois):
    n = len(pois)
    matrix = [[0] * (n+1) for _ in range(n+1)]
    
    coords = [user_location] + [poi.location for poi in pois]
    
    for i in range(n+1):
        for j in range(n+1):
            if i != j:
                matrix[i][j] = haversine_distance(coords[i], coords[j])
    
    return matrix
```

### Combined Score Calculation

**POI đầu tiên:**
```
score = 0.1 × distance_score + 0.45 × similarity + 0.45 × rating
```

**POI giữa (High similarity ≥ 0.8):**
```
score = 0.15 × distance_score + 0.5 × similarity + 0.3 × rating + 0.05 × bearing_score
```

**POI giữa (Low similarity < 0.8):**
```
score = 0.25 × distance_score + 0.1 × similarity + 0.4 × rating + 0.25 × bearing_score
```

**POI cuối:**
```
score = 0.4 × distance_score + 0.3 × similarity + 0.3 × rating
```

## 🎯 Tính năng mới

### 1. Route Mode (🗺️)
- Xem route hoàn chỉnh
- Hiển thị bearing angle trên mỗi đoạn
- Format: `XXX°` ở giữa mỗi arrow

### 2. Analyze Mode (🔍)
- Click vào POI để phân tích chi tiết
- Hiển thị:
  - ✅ Công thức tính score với giá trị thực
  - ✅ Giải thích bearing (vector 1 vs vector 2)
  - ✅ Distance matrix của route
  - ✅ So sánh với top 8 POI candidates
  - ✅ Lý do chọn POI này

### 3. Visualization
- Bearing lines từ current position đến tất cả POIs
- Arc vẽ góc Δ giữa 2 vectors (màu tím)
- POI selected highlight màu xanh lá

## 🧪 Testing

### Test Bearing Calculation

```python
from route_algorithm import GeographicUtils

geo = GeographicUtils()

# Test 1: North direction
bearing = geo.calculate_bearing(21.0, 105.0, 22.0, 105.0)
print(f"North: {bearing}°")  # Should be ~0°

# Test 2: East direction  
bearing = geo.calculate_bearing(21.0, 105.0, 21.0, 106.0)
print(f"East: {bearing}°")  # Should be ~90°

# Test 3: Bearing difference
diff = geo.calculate_bearing_difference(350, 10)
print(f"Diff: {diff}°")  # Should be 20°
```

### Test Route Building

```python
from route_algorithm import RouteCalculator, POI

pois = [
    POI(id="1", name="Cafe A", category="Cafe", lat=21.03, lon=105.85, score=0.9, rating=0.8),
    POI(id="2", name="Museum B", category="Museum", lat=21.04, lon=105.86, score=0.85, rating=0.9),
    # ... more POIs
]

calculator = RouteCalculator()
route = calculator.build_route(
    pois=pois,
    user_location=(21.0285, 105.8542),
    target_count=5,
    max_radius=2000
)

print(f"Route: {[p['name'] for p in route]}")
```

## 📝 API Endpoints

### POST /api/build_route

**Request:**
```json
{
  "pois": [...],
  "user_location": {"lat": 21.0285, "lon": 105.8542},
  "target_count": 5,
  "max_radius": 2000
}
```

**Response:**
```json
{
  "route": [...],
  "distance_matrix": [[...]]
}
```

### POST /api/calculate_distance_matrix

**Request:**
```json
{
  "user_location": {"lat": 21.0285, "lon": 105.8542},
  "pois": [...]
}
```

**Response:**
```json
{
  "distance_matrix": [[...]],
  "labels": ["USER", "POI 1", "POI 2", ...]
}
```

## 🐛 Troubleshooting

### Port 5000 already in use
```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9

# Or use different port
python route_algorithm.py --port 5001
```

### CORS errors
- Make sure Flask-CORS is installed
- Check browser console for errors
- Backend server must be running

### Distance matrix không hiển thị
- Check console log: `console.log('Distance Matrix:', distanceMatrix)`
- Verify route đã được build
- Check POI coordinates hợp lệ

## 📚 References

- Haversine formula: https://en.wikipedia.org/wiki/Haversine_formula
- Bearing calculation: https://www.movable-type.co.uk/scripts/latlong.html
- Greedy algorithm: https://en.wikipedia.org/wiki/Greedy_algorithm
