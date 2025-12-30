# Location Search API

API tìm kiếm địa điểm gần nhất theo tọa độ và phương tiện di chuyển.

## Cấu trúc project

```
Demo_project/
├── config/                 # Cấu hình ứng dụng
│   ├── __init__.py
│   └── config.py          # Cấu hình tổng hợp (database, transportation modes, etc.)
│
├── Logic/                  # Các hàm logic thuần túy
│   ├── __init__.py
│   └── radius_search.py   # Hàm tìm kiếm địa điểm theo bán kính
│
├── Service/                # Service layer xử lý business logic
│   ├── __init__.py
│   └── location_service.py # Service xử lý tìm kiếm địa điểm
│
└── Router/                 # API endpoints
    └── v1/
        └── api_server.py  # FastAPI endpoints
```

## Luồng xử lý

1. **API Layer** (`Router/v1/api_server.py`): 
   - Nhận request từ client
   - Validate input
   - Gọi Service layer
   - Trả response

2. **Service Layer** (`Service/location_service.py`):
   - Xử lý business logic
   - Validate transportation mode
   - Gọi các hàm trong Logic layer
   - Format kết quả

3. **Logic Layer** (`Logic/radius_search.py`):
   - Chứa các hàm thuần túy
   - Query database
   - Tính toán bán kính động

## Cài đặt

```bash
# Cài đặt dependencies
pip install fastapi uvicorn psycopg2 python-dotenv pydantic

# Tạo file .env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=demo_p3
DB_USER=postgres
DB_PASSWORD=your_password
```

## Chạy API

```bash
cd Router/v1
python api_server.py
```

API sẽ chạy tại: http://localhost:8000

## API Endpoints

### POST /api/v1/locations/search

Tìm k điểm gần nhất xung quanh tọa độ.

**Request:**
```json
{
  "latitude": 21.0285,
  "longitude": 105.8542,
  "transportation_mode": "WALKING",
  "top_k": 10
}
```

**Response:**
```json
{
  "status": "success",
  "transportation_mode": "WALKING",
  "center": {
    "latitude": 21.0285,
    "longitude": 105.8542
  },
  "radius_used": 650,
  "total_results": 10,
  "results": [
    {
      "id": 123,
      "poi_type": "Cafe",
      "distance_meters": 150.5,
      "lat": 21.0290,
      "lon": 105.8545
    }
  ]
}
```

## Cấu hình

Trong `config/config.py`, bạn có thể điều chỉnh:

- `TOP_K_RESULTS`: Số lượng điểm mặc định trả về (10)
- `TRANSPORTATION_CONFIG`: Cấu hình bán kính cho từng phương tiện:
  - WALKING: 500m - 1000m
  - BICYCLING: 2000m - 6000m
  - TRANSIT: 2000m - 15000m
  - FLEXIBLE: 2000m - 20000m
  - DRIVING: 2000m - 10000m

## Transportation Modes

- `WALKING`: Đi bộ
- `BICYCLING`: Xe đạp
- `TRANSIT`: Phương tiện công cộng
- `FLEXIBLE`: Linh hoạt
- `DRIVING`: Lái xe
