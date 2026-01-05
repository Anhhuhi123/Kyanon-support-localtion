# Map API - Location Search & Route Planning System

API tìm kiếm địa điểm và lập kế hoạch lộ trình sử dụng công nghệ H3 hexagonal indexing, Redis caching, và Qdrant vector search.

## 🏗️ Cấu trúc Project

```
Map/
├── main.py                          # Entry point chính của ứng dụng
├── requirements.txt                  # Dependencies
├── README.md                        # Tài liệu hướng dẫn
│
├── config/                          # Cấu hình
│   ├── __init__.py
│   └── config.py                    # Cấu hình database, Qdrant, Redis, H3
│
├── Router/v1/                       # API Endpoints (FastAPI)
│   ├── api_server.py                # Main FastAPI app
│   ├── location_api.py              # Spatial search endpoints
│   └── semantic_api.py              # Semantic search endpoints
│
├── Service/                         # Business Logic Layer
│   ├── location_service.py          # Service cho spatial search
│   └── semantic_search_service.py   # Service cho semantic search & route planning
│
├── Logic/                           # Core Logic
│   ├── h3_radius_search.py          # H3 + Redis search algorithm
│   ├── radius_search.py             # PostGIS radius search
│   ├── Route.py                     # Route building với Greedy algorithm
│   └── Information_location.py      # Location info service với connection pooling
│
├── retrieval/                       # Vector Store & Embeddings
│   ├── qdrant_vector_store.py       # Qdrant client wrapper
│   └── embeddings.py                # Sentence Transformer embeddings
│
└── scripts/                         # Utility Scripts
    └── ingest_poi_to_qdrant.py      # Script để ingest POI vào Qdrant
```

---

## 📄 Chi tiết từng file

### **1. main.py**
**Nhiệm vụ:** Entry point của ứng dụng
- Khởi động Uvicorn server
- Load FastAPI app từ `Router.v1.api_server`
- Chạy ở port 8000 với hot reload

### **2. config/config.py**
**Nhiệm vụ:** Quản lý cấu hình tập trung
- **Database:** PostgreSQL connection (host, port, database name, credentials)
- **Qdrant:** Vector database config (URL, API key, collection name, dimension)
- **Redis:** Cache config (host, port, TTL)
- **H3:** Hexagonal indexing resolution và k-ring cho từng phương tiện
- **Embedding Model:** Sentence Transformer model config
- **Transportation Modes:** Cấu hình bán kính tìm kiếm cho từng phương tiện (WALKING, BICYCLING, TRANSIT, FLEXIBLE, DRIVING)

**Classes:**
- `TransportationMode`: Enum định nghĩa các phương tiện
- `Config`: Class chứa tất cả cấu hình và validation methods

---

### **3. Router/v1/api_server.py**
**Nhiệm vụ:** Main FastAPI application
- Khởi tạo FastAPI app với metadata
- Include routers từ `location_api` và `semantic_api`
- Startup event để init services (singleton pattern)
- Root endpoint `/` và health check `/health`

### **4. Router/v1/location_api.py**
**Nhiệm vụ:** API endpoints cho spatial search (PostGIS)
- **POST `/api/v1/locations/search`**: Tìm tất cả địa điểm trong bán kính (>= 50 điểm)

**Request Body:**
```json
{
  "latitude": 10.8294811,
  "longitude": 106.7737852,
  "transportation_mode": "WALKING"
}
```

### **5. Router/v1/semantic_api.py**
**Nhiệm vụ:** API endpoints cho semantic search và route planning

**Endpoints:**

#### **POST `/api/v1/semantic/search`**
Tìm kiếm địa điểm theo ngữ nghĩa (không filter theo vị trí)

**Request:**
```json
{
  "query": "Travel",
  "top_k": 10
}
```

#### **POST `/api/v1/semantic/combined`**
Tìm kiếm kết hợp: Spatial + Semantic

**Request:**
```json
{
  "latitude": 10.8294811,
  "longitude": 106.7737852,
  "transportation_mode": "WALKING",
  "semantic_query": "cafe phù hợp làm việc",
  "top_k": 10
}
```

#### **POST `/api/v1/semantic/routes`**
Xây dựng lộ trình tối ưu

**Request:**
```json
{
  "latitude": 10.8294811,
  "longitude": 106.7737852,
  "transportation_mode": "WALKING",
  "semantic_query": "cafe phù hợp làm việc",
  "max_time_minutes": 180,
  "target_places": 5,
  "max_routes": 3,
  "top_k_semantic": 10
}
```

---

### **6. Service/location_service.py**
**Nhiệm vụ:** Business logic cho spatial search
- Sử dụng `H3RadiusSearch` để tìm địa điểm
- Validate transportation mode
- Trả về tất cả địa điểm trong bán kính (>= 50 nếu có đủ)
- Tính execution time

### **7. Service/semantic_search_service.py**
**Nhiệm vụ:** Business logic cho semantic search và route planning

**Methods:**
- `search_by_query()`: Tìm kiếm ngữ nghĩa thuần túy
- `search_combined()`: Kết hợp spatial + semantic
- `search_combined_with_routes()`: Build lộ trình tối ưu

**Workflow:**
1. Spatial search → Lấy địa điểm gần
2. Semantic search → Filter theo ngữ nghĩa
3. Route building → Xây dựng lộ trình Greedy

---

### **8. Logic/h3_radius_search.py**
**Nhiệm vụ:** Tìm kiếm địa điểm sử dụng H3 + Redis cache

**Class:** `H3RadiusSearch`

**Features:**
- Chuyển (lat, lon) → H3 cell index
- Tìm k-ring (các hexagon lân cận)
- Cache POI data trong Redis (TTL configurable)
- Fallback sang PostgreSQL nếu cache miss
- Haversine distance calculation

**Methods:**
- `search_locations()`: Main search method
- `get_k_ring_for_mode()`: Lấy k-ring value theo phương tiện
- `calculate_distance_haversine()`: Tính khoảng cách

### **9. Logic/radius_search.py**
**Nhiệm vụ:** Tìm kiếm địa điểm sử dụng PostGIS (legacy)

**Functions:**
- `search_locations()`: Tìm tất cả địa điểm trong bán kính tăng dần
- `_query_locations_within_radius()`: Query PostGIS ST_DWithin

**Note:** File này được giữ lại cho compatibility, production sử dụng H3 search

### **10. Logic/Route.py**
**Nhiệm vụ:** Xây dựng lộ trình tối ưu với Greedy algorithm

**Class:** `RouteBuilder`

**Algorithm:**
1. Chọn điểm xuất phát có `combined_score` cao nhất
2. Chọn các điểm tiếp theo từ vị trí hiện tại
3. Điểm cuối phải gần user (< 20% max_distance)

**Combined Score Formula:**
```
combined_score = 0.7 × normalized_score + 0.3 × (1 - normalized_distance)
```

**Methods:**
- `build_routes()`: Xây dựng nhiều lộ trình
- `build_distance_matrix()`: Tạo ma trận khoảng cách Haversine
- `calculate_travel_time()`: Tính thời gian di chuyển theo phương tiện
- `get_stay_time()`: Thời gian tham quan (mặc định 30 phút)

### **11. Logic/Information_location.py**
**Nhiệm vụ:** Lấy thông tin chi tiết địa điểm từ PostgreSQL

**Class:** `LocationInfoService`

**Features:**
- Connection pooling (10-30 connections)
- Batch query optimization
- Thread-safe

**Methods:**
- `get_location_by_id()`: Lấy 1 địa điểm
- `get_locations_by_ids()`: Lấy nhiều địa điểm (batch)

---

### **12. retrieval/qdrant_vector_store.py**
**Nhiệm vụ:** Wrapper cho Qdrant vector database

**Class:** `QdrantVectorStore`

**Features:**
- Kết nối Qdrant server
- Create/manage collections
- Add embeddings with metadata
- Search với filters (MatchAny, HasIdCondition)
- Batch upload optimization

**Methods:**
- `create_index()`: Tạo collection
- `add_embeddings()`: Upload vectors
- `search()`: Vector similarity search
- `search_with_filters()`: Search với ID filter

### **13. retrieval/embeddings.py**
**Nhiệm vụ:** Generate text embeddings

**Class:** `EmbeddingGenerator`

**Features:**
- Sử dụng Sentence Transformers (multilingual-e5-small/large)
- Support batch encoding
- Normalize embeddings (cosine similarity)
- Prefix handling: `passage:` cho documents, `query:` cho queries
- GPU/CPU auto-detect

**Methods:**
- `generate_embeddings()`: Batch generation
- `generate_single_embedding()`: Single query embedding

---

### **14. scripts/ingest_poi_to_qdrant.py**
**Nhiệm vụ:** Script để import POI data vào Qdrant

**Workflow:**
1. Query `id` và `poi_type` từ PostgreSQL
2. Generate embeddings từ `poi_type`
3. Upload vào Qdrant với:
   - `point.id` = location id
   - `payload` = `{"poi_type": "..."}`

**Usage:**
```bash
python scripts/ingest_poi_to_qdrant.py
```

---

## 🚀 Cách sử dụng

### **1. Cài đặt Dependencies**
```bash
cd Map
pip install -r requirements.txt
```

### **2. Cấu hình Environment Variables**
Tạo file `.env`:
```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=demo_p3
DB_USER=postgres
DB_PASSWORD=your_password

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_api_key

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Embedding Model
EMBEDDING_MODEL=intfloat/multilingual-e5-small
```

### **3. Khởi động các Services**

#### **PostgreSQL** (port 5432)
```bash
# Đảm bảo database có table poi_locations với columns:
# id, name, lat, long, address, poi_type, normalize_stars_reviews
```

#### **Redis** (port 6379)
```bash
redis-server
```

#### **Qdrant** (port 6333)
```bash
docker run -p 6333:6333 qdrant/qdrant
```

### **4. Ingest Data vào Qdrant**
```bash
python scripts/ingest_poi_to_qdrant.py
```

### **5. Khởi động API Server**
```bash
python main.py
```

Server sẽ chạy tại: **http://localhost:8000**

---

## 📡 API Endpoints

### **1. Spatial Search (Tìm kiếm theo vị trí)**
```bash
curl -X POST "http://localhost:8000/api/v1/locations/search" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 10.8294811,
    "longitude": 106.7737852,
    "transportation_mode": "WALKING"
  }'
```

**Response:**
```json
{
  "status": "success",
  "transportation_mode": "WALKING",
  "center": {"latitude": 10.8294811, "longitude": 106.7737852},
  "radius_used": 4300,
  "total_results": 52,
  "results": [
    {
      "id": "A1",
      "name": "Cafe ABC",
      "poi_type": "cafe",
      "address": "123 Nguyen Hue",
      "lat": 10.830,
      "lon": 106.774,
      "distance_meters": 150
    }
  ]
}
```

---

### **2. Semantic Search (Tìm kiếm theo ngữ nghĩa)**
```bash
curl -X POST "http://localhost:8000/api/v1/semantic/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cafe phù hợp làm việc",
    "top_k": 10
  }'
```

**Response:**
```json
{
  "status": "success",
  "query": "cafe phù hợp làm việc",
  "total_results": 10,
  "results": [
    {
      "id": "A1",
      "name": "Highlands Coffee",
      "score": 0.92,
      "poi_type": "cafe",
      "address": "...",
      "lat": 10.77,
      "lon": 106.70
    }
  ]
}
```

---

### **3. Combined Search (Kết hợp Spatial + Semantic)**
```bash
curl -X POST "http://localhost:8000/api/v1/semantic/combined" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 10.8294811,
    "longitude": 106.7737852,
    "transportation_mode": "WALKING",
    "semantic_query": "quán cafe view đẹp",
    "top_k": 5
  }'
```

**Response:**
```json
{
  "status": "success",
  "spatial_search": {
    "transportation_mode": "WALKING",
    "radius_used": 4300,
    "total_found": 52
  },
  "semantic_search": {
    "query": "quán cafe view đẹp",
    "total_results": 5,
    "results": [
      {
        "id": "C3",
        "name": "The Coffee House",
        "score": 0.95,
        "distance_meters": 450,
        "poi_type": "cafe"
      }
    ]
  }
}
```

---

### **4. Route Planning (Xây dựng lộ trình)**
```bash
curl -X POST "http://localhost:8000/api/v1/semantic/routes" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 10.8294811,
    "longitude": 106.7737852,
    "transportation_mode": "BICYCLING",
    "semantic_query": "khám phá ẩm thực địa phương",
    "max_time_minutes": 180,
    "target_places": 5,
    "max_routes": 3,
    "top_k_semantic": 10
  }'
```

**Response:**
```json
{
  "status": "success",
  "total_routes": 3,
  "routes": [
    {
      "route_id": 1,
      "total_time_minutes": 165,
      "travel_time_minutes": 35,
      "stay_time_minutes": 130,
      "total_score": 4.6,
      "avg_score": 0.92,
      "efficiency": 2.79,
      "places": [
        {
          "order": 1,
          "place_id": "R1",
          "place_name": "Phở Hòa",
          "poi_type": "restaurant",
          "score": 0.95,
          "lat": 10.831,
          "lon": 106.775,
          "travel_time_minutes": 5,
          "stay_time_minutes": 30,
          "distance_from_prev_meters": 250
        }
      ]
    }
  ]
}
```

---

## 🔧 Các phương tiện di chuyển (Transportation Modes)

| Mode | H3 K-Ring | Coverage Radius | Use Case |
|------|-----------|-----------------|----------|
| **WALKING** | 15 | ~4.3 km | Đi bộ |
| **BICYCLING** | 30 | ~8.6 km | Đi xe đạp |
| **TRANSIT** | 40 | ~11.5 km | Phương tiện công cộng |
| **FLEXIBLE** | 60 | ~17.2 km | Linh hoạt |
| **DRIVING** | 100 | ~28.7 km | Lái xe |

---

## 🎯 Công nghệ sử dụng

- **FastAPI**: Web framework
- **PostgreSQL + PostGIS**: Spatial database
- **Qdrant**: Vector database cho semantic search
- **Redis**: Caching layer
- **H3**: Uber's hexagonal hierarchical geospatial indexing system
- **Sentence Transformers**: Text embeddings (E5 model)
- **Haversine**: Distance calculation

---

## 📊 Performance

- **H3 + Redis Cache**: Sub-second response cho repeated queries
- **Connection Pooling**: 10-30 PostgreSQL connections
- **Batch Processing**: Optimized batch queries và embedding generation
- **Greedy Algorithm**: O(n²) route building

---

## 📖 API Documentation

Sau khi khởi động server, truy cập:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🐛 Troubleshooting

### Lỗi kết nối Qdrant
```bash
# Kiểm tra Qdrant đang chạy
curl http://localhost:6333/collections
```

### Lỗi Redis connection
```bash
# Test Redis
redis-cli ping
# Output: PONG
```

### Lỗi PostgreSQL
```bash
# Kiểm tra connection
psql -h localhost -U postgres -d demo_p3
```

---

## 👥 Contributors

Developed by Kyanon Team
