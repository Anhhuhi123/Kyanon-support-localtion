# Location Search & Route Planning API

API tìm kiếm địa điểm và lập kế hoạch lộ trình tối ưu sử dụng **Async Architecture**, **H3 Hexagonal Indexing**, **Redis Caching**, **Qdrant Vector Search**, và **PostgreSQL/PostGIS**.

## 🏗️ Cấu trúc Project

```
Kyanon-support-localtion/
├── main.py                          # Entry point - khởi động Uvicorn server
├── server.py                        # FastAPI app initialization & lifecycle management
├── requirements.txt                 # Python dependencies
├── docker-compose.yml               # Docker services orchestration
├── Dockerfile                       # Container configuration
├── README.md                        # Project documentation
│
├── config/                          # Configuration Management
│   ├── __init__.py
│   ├── config.py                    # Centralized config (DB, Qdrant, Redis, H3)
│   └── db.py                        # Async connection pools (PostgreSQL, Redis)
│
├── routers/v1/                      # API Endpoints (FastAPI Routers)
│   ├── location_api.py              # Spatial search endpoints (PostGIS)
│   ├── route_api.py                 # Semantic search & route planning endpoints
│   └── poi_api.py                   # POI management & replacement endpoints
│
├── services/                        # Business Logic Layer (Async Service Pattern)
│   ├── __init__.py
│   ├── location_search.py           # Spatial search service (H3 + PostGIS)
│   ├── qdrant_search.py             # Base semantic search service (Qdrant)
│   ├── spatial_search.py            # Combined spatial + semantic search
│   ├── route_search.py              # Route building & POI replacement logic
│   ├── route_service.py             # Facade service (backward compatibility)
│   ├── poi_service.py               # POI CRUD & user preferences management
│   ├── cache_search.py              # Redis caching layer
│   └── ingest_poi_to_qdrant.py      # POI ingestion to Qdrant service
│
├── radius_logic/                    # Core Algorithm Implementations
│   ├── h3_radius_search.py          # H3 hexagonal indexing + Redis cache
│   ├── information_poi.py      # POI info retrieval (async pooling)
│   ├── replace_poi.py               # POI replacement selection logic
│   ├── route.py                     # Route builder (Greedy algorithm)
│   └── route/                       # Route building sub-modules
│       ├── route_config.py          # Route configuration constants
│       ├── geographic_utils.py      # Haversine distance calculations
│       ├── poi_validator.py         # POI validation (opening hours, etc.)
│       ├── calculator.py            # Time/distance calculations
│       ├── route_builder_target.py  # Target-based route building
│       └── route_builder_duration.py # Duration-based route building
│
├── retrieval/                       # Vector Store & Embeddings
│   ├── __init__.py
│   ├── qdrant_vector_store.py       # Async Qdrant client wrapper
│   └── embeddings.py                # Sentence Transformer (E5 model)
│
├── pydantics/                       # Request/Response Schemas (Pydantic)
│   ├── location.py                  # Spatial search schemas
│   ├── route.py                     # Route & semantic search schemas
│   ├── poi.py                       # POI management schemas
│   └── user.py                      # User-related schemas
│
├── utils/                           # Utility Functions
│   ├── time_utils.py                # Opening hours validation & time parsing
│   ├── data_processing.py           # POI data transformation
│   ├── new_data_processing.py       # Enhanced POI processing
│   └── llm.py                       # LLM integration (OpenAI)
│
├── scripts/                         # Maintenance & Data Scripts
│   ├── migration.py                 # Database migration scripts
│   ├── test_open_hours_type.py      # Opening hours testing
│   ├── ingest_db/                   # Database ingestion scripts
│   ├── ingest_qdrant/               # Qdrant data ingestion
│   ├── clean_data/                  # Data cleaning utilities
│   └── test/                        # Integration tests
│
└── docs/                            # Documentation
    └── ROUTE_SYSTEM_GUIDE.md        # Route system detailed guide
```

---

## 📄 Kiến trúc hệ thống

### **Async Architecture Pattern**

Hệ thống sử dụng **fully async architecture** để tối ưu performance:

```
Client Request
    ↓
FastAPI Router (async)
    ↓
Service Layer (async) → Redis Cache (async)
    ↓                        ↓
Business Logic           Cache Hit → Return
    ↓
Multiple Data Sources (parallel async)
├── PostgreSQL (asyncpg pool)
├── Qdrant (AsyncQdrantClient)
└── Redis (aioredis)
```

### **Service Layer Architecture**

**Facade Pattern** với inheritance hierarchy:

```
RouteService (Facade)
    ↓
    ├── QdrantSearch (Base Service)
    │   └── Semantic search core logic
    │
    ├── SpatialSearch (extends QdrantSearch)
    │   └── Spatial + Semantic combined search
    │
    └── RouteSearch (extends SpatialSearch)
        └── Route building + POI replacement
```

---

## 📄 Chi tiết từng module

### **1. server.py**
**Nhiệm vụ:** FastAPI application lifecycle management

**Features:**
- Async startup/shutdown event handlers
- Initialize async connection pools (PostgreSQL, Redis)
- Singleton service initialization
- Shared resource management (QdrantVectorStore, EmbeddingGenerator)
- Health check endpoints với dependency validation

**Startup Flow:**
```python
1. Init async PostgreSQL pool (asyncpg)
2. Init async Redis client (aioredis)
3. Init AsyncQdrantClient
4. Init QdrantVectorStore với async client
5. Init EmbeddingGenerator (singleton)
6. Init all services với shared resources
7. Set service instances to router modules
```

### **2. main.py**
**Nhiệm vụ:** Entry point
- Khởi động Uvicorn server
- Hot reload trong development mode
- Load server:app (FastAPI instance)

---

### **3. config/config.py**
**Nhiệm vụ:** Centralized configuration management

**Configuration Sections:**
- **Database:** PostgreSQL connection parameters
- **Qdrant:** Vector DB URL, API key, collection name, dimensions
- **Redis:** Cache server config, TTL settings
- **H3:** Resolution levels và k-ring values per transportation mode
- **Embedding:** Sentence Transformer model selection
- **Transportation Modes:** Radius configuration cho từng phương tiện

**Classes:**
- `TransportationMode`: Enum cho các loại phương tiện
- `Config`: Static configuration class với validation

### **4. config/db.py**
**Nhiệm vụ:** Async connection pool management

**Features:**
- Global async PostgreSQL connection pool (asyncpg)
- Global async Redis client (aioredis)
- Pool lifecycle management (init/close)
- Connection pooling: 2-10 connections
- Command timeout: 60s

---

## 🌐 API Endpoints

### **A. Location API** (`/api/v1/locations`)

#### **POST `/search`**
Spatial search - Tìm TẤT CẢ địa điểm gần nhất (>= 50) trong bán kính

**Request:**
```json
{
  "latitude": 10.8294811,
  "longitude": 106.7737852,
  "transportation_mode": "WALKING"
}
```

**Response:**
```json
{
  "status": "success",
  "transportation_mode": "WALKING",
  "center": {"latitude": 10.8294811, "longitude": 106.7737852},
  "radius_used": 4300,
  "total_results": 52,
  "execution_time_seconds": 0.15,
  "results": [
    {
      "id": "A1",
      "name": "Cafe ABC",
      "poi_type": "cafe",
      "address": "123 Nguyen Hue",
      "lat": 10.830,
      "lon": 106.774,
      "distance_meters": 150,
      "score": 4.5,
      "open_hours": "08:00-22:00"
    }
  ]
}
```

---

### **B. Route API** (`/api/v1/route`)

#### **POST `/search`**
Pure semantic search - Tìm kiếm theo ngữ nghĩa (không filter vị trí)

**Request:**
```json
{
  "query": "cafe phù hợp làm việc",
  "top_k": 10
}
```

**Response:**
```json
{
  "status": "success",
  "query": "cafe phù hợp làm việc",
  "total_results": 10,
  "execution_time_seconds": 0.08,
  "results": [
    {
      "id": "C1",
      "name": "Highlands Coffee",
      "score": 0.92,
      "poi_type": "cafe",
      "lat": 10.77,
      "lon": 106.70
    }
  ]
}
```

#### **POST `/combined`**
Combined search - Spatial (PostGIS) + Semantic (Qdrant)

**Request:**
```json
{
  "latitude": 10.8294811,
  "longitude": 106.7737852,
  "transportation_mode": "BICYCLING",
  "semantic_query": "quán cafe view đẹp",
  "top_k_semantic": 10
}
```

**Response:**
```json
{
  "status": "success",
  "spatial_search": {
    "transportation_mode": "BICYCLING",
    "radius_used": 8600,
    "total_found": 75
  },
  "semantic_search": {
    "query": "quán cafe view đẹp",
    "top_k": 10,
    "results": [...]
  },
  "execution_time_seconds": 0.25
}
```

#### **POST `/routes`**
Route planning - Xây dựng lộ trình tối ưu với opening hours validation

**Request:**
```json
{
  "latitude": 10.8294811,
  "longitude": 106.7737852,
  "transportation_mode": "BICYCLING",
  "semantic_query": "khám phá ẩm thực địa phương",
  "user_id": "uuid-optional",
  "max_time_minutes": 180,
  "target_places": 5,
  "max_routes": 3,
  "top_k_semantic": 10,
  "customer_like": false,
  "duration_mode": false,
  "current_datetime": "2026-02-05T14:00:00"
}
```

**Response:**
```json
{
  "status": "success",
  "total_routes": 3,
  "execution_time_seconds": 1.2,
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
          "distance_from_prev_meters": 250,
          "is_open": true
        }
      ]
    }
  ]
}
```

#### **POST `/replace-poi`**
Replace single POI in route - Tìm POI thay thế phù hợp

**Request:**
```json
{
  "user_id": "uuid",
  "route_id": 1,
  "old_poi_id": "R1",
  "user_location": {"latitude": 10.83, "longitude": 106.77},
  "transportation_mode": "WALKING",
  "top_k": 3,
  "current_datetime": "2026-02-05T15:00:00"
}
```

#### **POST `/replace-full-route`**
Replace entire route - Tìm route mới hoàn toàn với semantic query mới

**Request:**
```json
{
  "user_id": "uuid",
  "route_id": 1,
  "new_semantic_query": "quán cafe yên tĩnh",
  "user_location": {"latitude": 10.83, "longitude": 106.77},
  "transportation_mode": "WALKING",
  "max_time_minutes": 120,
  "target_places": 4,
  "current_datetime": "2026-02-05T16:00:00"
}
```

---

### **C. POI API** (`/api/v1/poi`)

#### **POST `/visited`**
Get visited POIs by user

**Request:**
```json
{
  "user_id": "uuid"
}
```

#### **POST `/confirm-replace`**
Confirm POI replacement and update cache

**Request:**
```json
{
  "user_id": "uuid",
  "route_id": 1,
  "old_poi_id": "A1",
  "new_poi_id": "A2"
}
```

#### **POST `/update-poi-clean`**
Sync POI changes to Qdrant (add/delete/update)

**Request:**
```json
{
  "add": ["id1", "id2"],
  "delete": ["id3"],
  "update": ["id4"]
}
```

---

## � Service Layer Chi tiết

### **A. services/qdrant_search.py**
**Nhiệm vụ:** Base service cho semantic search

**Class:** `QdrantSearch`

**Features:**
- Singleton pattern cho vector_store và embedder
- Pure semantic search (không filter vị trí)
- Async Qdrant operations
- Redis cache integration

**Methods:**
- `search_by_query(query, top_k)`: Tìm kiếm ngữ nghĩa thuần túy

---

### **B. services/spatial_search.py**
**Nhiệm vụ:** Combined spatial + semantic search service

**Class:** `SpatialSearch` (extends `QdrantSearch`)

**Features:**
- Kết hợp H3 radius search + Qdrant semantic search
- Support multiple semantic queries (split by comma)
- Deduplicate POI results
- Customer preference handling (auto-add "Culture & heritage")

**Methods:**
- `search_combined()`: Spatial + single semantic query
- `search_multi_queries_and_find_locations()`: Spatial + multiple queries
- `_split_queries()`: Parse comma-separated queries

---

### **C. services/route_search.py**
**Nhiệm vụ:** Route building + POI replacement logic

**Class:** `RouteSearch` (extends `SpatialSearch`)

**Features:**
- Greedy algorithm route building (async)
- Opening hours validation
- POI replacement with candidates
- Full route replacement
- Route caching (Redis)
- Process pool for CPU-bound tasks

**Methods:**
- `build_routes()`: Build multiple optimal routes
- `replace_poi()`: Find replacement POI candidates
- `replace_full_route()`: Replace entire route with new query
- `confirm_replace_poi()`: Confirm replacement and update cache

**Route Building Workflow:**
```
1. Spatial + Semantic search → Get candidates
2. Filter by opening hours (optional)
3. Build routes with Greedy algorithm (process pool)
4. Validate opening hours in routes
5. Cache routes in Redis
6. Return top N routes
```

---

### **D. services/route_service.py**
**Nhiệm vụ:** Facade service (backward compatibility)

**Class:** `RouteService`

**Pattern:** Facade Pattern

**Delegates to:**
- `QdrantSearch`: Pure semantic search
- `SpatialSearch`: Combined search
- `RouteSearch`: Route building & replacement

**Purpose:** Maintain backward compatibility while using new modular architecture

---

### **E. services/location_search.py**
**Nhiệm vụ:** Spatial search service (PostGIS + H3)

**Class:** `LocationSearch`

**Features:**
- H3 radius search với Redis cache
- Progressive radius expansion (đến khi tìm được >= 50 POI)
- Async database operations
- Haversine distance calculation

**Methods:**
- `find_nearest_locations()`: Main spatial search
- `_query_locations_within_radius()`: PostGIS ST_DWithin query

---

### **F. services/poi_service.py**
**Nhiệm vụ:** POI management & user preferences

**Class:** `PoiService`

**Features:**
- Get visited POIs by user
- Batch POI info retrieval
- POI description generation (LLM)
- POI data cleaning & processing
- Update POI to Qdrant (sync)

**Methods:**
- `get_visited_pois_by_user()`: User visit history
- `get_poi_by_ids()`: Batch POI retrieval
- `update_poi()`: Add/update/delete POIs
- `generate_description_batch()`: LLM-based descriptions

---

### **G. services/cache_search.py**
**Nhiệm vụ:** Redis caching layer

**Class:** `CacheSearch`

**Features:**
- Route cache management
- TTL-based expiration
- JSON serialization/deserialization
- Async Redis operations

**Methods:**
- `get_cached_route()`: Retrieve cached route
- `cache_route()`: Store route in cache
- `clear_cache()`: Invalidate cache

---

### **H. services/ingest_poi_to_qdrant.py**
**Nhiệm vụ:** POI ingestion to Qdrant service

**Class:** `IngestPoiToQdrantService`

**Features:**
- Batch POI ingestion
- Embedding generation
- Qdrant point management (add/delete/update)
- Conflict resolution

**Methods:**
- `ingest_all_pois()`: Full ingestion
- `add_pois()`: Add new POIs
- `delete_pois()`: Remove POIs
- `update_pois()`: Update existing POIs

---

## 🧠 Core Logic Modules

### **A. radius_logic/h3_radius_search.py**
**Nhiệm vụ:** H3 hexagonal indexing + Redis cache

**Class:** `H3RadiusSearch`

**H3 Algorithm:**
```
1. Convert (lat, lon) → H3 cell index (resolution 9)
2. Get k-ring (neighboring hexagons) based on transportation mode
3. Cache lookup: Check Redis for POI data per H3 cell
4. Cache miss: Query PostgreSQL, cache result (TTL)
5. Calculate Haversine distance from center
6. Return sorted by distance
```

**K-Ring Values:**
| Mode | K-Ring | Coverage |
|------|--------|----------|
| WALKING | 15 | ~4.3 km |
| BICYCLING | 30 | ~8.6 km |
| TRANSIT | 40 | ~11.5 km |
| FLEXIBLE | 60 | ~17.2 km |
| DRIVING | 100 | ~28.7 km |

---

### **B. radius_logic/route.py**
**Nhiệm vụ:** Route building with Greedy algorithm

**Class:** `RouteBuilder`

**Sub-modules:**
- `route/route_config.py`: Constants (stay time, speed, etc.)
- `route/geographic_utils.py`: Haversine distance
- `route/poi_validator.py`: Opening hours validation
- `route/calculator.py`: Time/distance calculations
- `route/route_builder_target.py`: Target-based routes
- `route/route_builder_duration.py`: Duration-based routes

**Greedy Algorithm:**
```
1. Calculate distance matrix (Haversine)
2. Find start POI:
   - Highest combined_score
   - Within reasonable distance from user
3. Build route iteratively:
   - Select next POI with highest combined_score
   - Not visited yet
   - Within time budget
4. Find end POI:
   - Close to user (< 20% max distance)
   - High score
5. Calculate total time (travel + stay)
6. Repeat for max_routes
```

**Combined Score Formula:**
```
combined_score = 0.7 × normalized_score + 0.3 × (1 - normalized_distance)
```

**Async Support:**
- `build_routes_async()`: Async wrapper
- Uses `ProcessPoolExecutor` for CPU-bound computation

---

### **C. radius_logic/replace_poi.py**
**Nhiệm vụ:** POI replacement selection logic

**Class:** `POIUpdateService`

**Features:**
- Select top N replacement candidates
- Filter by opening hours (optional)
- Combined scoring: distance + rating
- Route time recalculation after replacement

**Candidate Scoring:**
```
1. Validate opening hours (if current_datetime provided)
2. Calculate distance from reference point
3. Normalize distance and rating
4. Combined score = 0.6 × normalized_rating + 0.4 × (1 - normalized_distance)
5. Sort by score descending
6. Return top N
```

**Methods:**
- `select_top_n_pois()`: Get top candidates
- `update_route_with_new_poi()`: Replace POI and recalculate times

---

### **D. radius_logic/information_poi.py**
**Nhiệm vụ:** POI info retrieval with async pooling

**Class:** `LocationInfoService`

**Features:**
- Async PostgreSQL connection pool
- Batch query optimization
- Redis cache integration (optional)
- Error handling & fallback

**Methods:**
- `get_locations_by_ids()`: Batch retrieval
- `get_location_by_id()`: Single POI
- `get_locations_with_type()`: Filter by poi_type

---

## 🗃️ Data Models (Pydantic Schemas)

### **pydantics/location.py**
- `LocationSearchRequest`: Spatial search input
- `LocationResponse`: POI data output

### **pydantics/route.py**
- `SemanticSearchRequest`: Semantic search input
- `CombinedSearchRequest`: Combined search input
- `RouteSearchRequest`: Route planning input
- `ReplacePOIRequest`: POI replacement input
- `ReplaceFullRouteRequest`: Full route replacement input
- `UpdatePOIRequest`: POI update input (deprecated)

### **pydantics/poi.py**
- `ConfirmReplaceRequest`: POI replacement confirmation
- `PoiRequest`: POI sync request (add/delete/update)

### **pydantics/user.py**
- `UserIdRequest`: User identification

---

## 🛠️ Utilities

### **utils/time_utils.py**
**Nhiệm vụ:** Opening hours validation

**Class:** `TimeUtils`

**Features:**
- Parse opening hours JSON
- Validate if POI is open at specific time
- Handle edge cases (24/7, closed, invalid format)
- Timezone-aware datetime handling

**Methods:**
- `is_open_at_time()`: Check if open
- `normalize_open_hours()`: Parse hours JSON
- `get_day_of_week()`: Get weekday index

---

### **utils/data_processing.py**
**Functions:**
- `process_poi_for_description()`: Transform POI data for LLM
- `process_ingest_to_poi_clean()`: Clean POI data before ingestion
- `get_default_opening_hours()`: Default hours fallback

---

### **utils/llm.py**
**Functions:**
- `process_batch()`: Batch LLM requests (OpenAI)
- Generate POI descriptions from structured data

---

## 🚀 Setup & Installation

### **1. Prerequisites**
- Python 3.9+
- PostgreSQL 13+ with PostGIS extension
- Redis 6+
- Qdrant 1.7+ (Docker recommended)

### **2. Clone Repository**
```bash
git clone <repository-url>
cd Kyanon-support-localtion
```

### **3. Install Dependencies**
```bash
python -m venv myenv
source myenv/bin/activate  # Windows: myenv\Scripts\activate
pip install -r requirements.txt
```

### **4. Environment Configuration**
Create `.env` file:
```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=location_db
DB_USER=postgres
DB_PASSWORD=your_password

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_api_key  # Optional
QDRANT_COLLECTION_NAME=poi_locations
VECTOR_DIMENSION=384

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_TTL=3600

# H3 Configuration
H3_RESOLUTION=9

# Embedding Model
EMBEDDING_MODEL=intfloat/multilingual-e5-small

# OpenAI (for description generation)
OPENAI_API_KEY=your_openai_key
```

### **5. Database Setup**
```sql
-- Create database
CREATE DATABASE location_db;

-- Enable PostGIS extension
CREATE EXTENSION postgis;

-- Create poi_clean table
CREATE TABLE poi_clean (
    id TEXT PRIMARY KEY,
    name TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    address TEXT,
    poi_type TEXT,
    description TEXT,
    open_hours JSONB,
    normalize_stars_reviews FLOAT,
    geometry GEOMETRY(Point, 4326)
);

-- Create spatial index
CREATE INDEX idx_poi_clean_geometry ON poi_clean USING GIST(geometry);

-- Create user tables (optional)
CREATE TABLE "UserItinerary" (
    id UUID PRIMARY KEY,
    "userId" UUID NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE "ItineraryPOI" (
    id UUID PRIMARY KEY,
    "itineraryId" UUID REFERENCES "UserItinerary"(id),
    "poiId" TEXT,
    visited BOOLEAN DEFAULT FALSE
);
```

### **6. Start Services**

#### **Option A: Docker Compose (Recommended)**
```bash
docker-compose up -d
```

This starts:
- PostgreSQL with PostGIS (port 5432)
- Redis (port 6379)
- Qdrant (port 6333)

#### **Option B: Manual Setup**

**Start Redis:**
```bash
redis-server
```

**Start Qdrant:**
```bash
docker run -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
```

### **7. Ingest Data to Qdrant**
```bash
# Ingest all POIs from database
python -m scripts.ingest_qdrant.ingest_all

# Or use the service endpoint (after server starts)
curl -X POST "http://localhost:8000/api/v1/poi/update-poi-clean" \
  -H "Content-Type: application/json" \
  -d '{"add": ["poi_id_1", "poi_id_2"]}'
```

### **8. Start API Server**
```bash
python main.py
```

Server will be available at:
- **API:** http://localhost:8000
- **Swagger Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## 📊 API Usage Examples

### **Example 1: Spatial Search (Find nearby places)**
```bash
curl -X POST "http://localhost:8000/api/v1/locations/search" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 10.8294811,
    "longitude": 106.7737852,
    "transportation_mode": "WALKING"
  }'
```

### **Example 2: Semantic Search (Find by query)**
```bash
curl -X POST "http://localhost:8000/api/v1/route/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cafe yên tĩnh phù hợp làm việc",
    "top_k": 10
  }'
```

### **Example 3: Combined Search**
```bash
curl -X POST "http://localhost:8000/api/v1/route/combined" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 10.8294811,
    "longitude": 106.7737852,
    "transportation_mode": "BICYCLING",
    "semantic_query": "khám phá thiên nhiên",
    "top_k_semantic": 10
  }'
```

### **Example 4: Build Route**
```bash
curl -X POST "http://localhost:8000/api/v1/route/routes" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 10.8294811,
    "longitude": 106.7737852,
    "transportation_mode": "WALKING",
    "semantic_query": "ẩm thực địa phương",
    "max_time_minutes": 180,
    "target_places": 5,
    "max_routes": 3,
    "top_k_semantic": 15,
    "current_datetime": "2026-02-05T14:00:00"
  }'
```

### **Example 5: Replace POI in Route**
```bash
curl -X POST "http://localhost:8000/api/v1/route/replace-poi" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "route_id": 1,
    "old_poi_id": "poi_123",
    "user_location": {
      "latitude": 10.83,
      "longitude": 106.77
    },
    "transportation_mode": "WALKING",
    "top_k": 3,
    "current_datetime": "2026-02-05T15:30:00"
  }'
```

### **Example 6: Get User Visited POIs**
```bash
curl -X POST "http://localhost:8000/api/v1/poi/visited" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

---

## 🎯 Transportation Modes & Coverage

| Mode | Speed (km/h) | K-Ring | Radius (km) | Use Case |
|------|--------------|--------|-------------|----------|
| **WALKING** | 5 | 15 | ~4.3 | Pedestrian exploration |
| **BICYCLING** | 15 | 30 | ~8.6 | Bike tours |
| **TRANSIT** | 20 | 40 | ~11.5 | Public transport |
| **FLEXIBLE** | 25 | 60 | ~17.2 | Mixed transportation |
| **DRIVING** | 40 | 100 | ~28.7 | Car trips |

---

## 🏗️ Architecture Patterns

### **1. Async Architecture**
- Fully async I/O operations
- Connection pooling (PostgreSQL, Redis)
- Non-blocking API handlers
- Async context managers

### **2. Service Layer Pattern**
- Separation of concerns
- Business logic in services
- Routers handle HTTP only
- Dependency injection

### **3. Facade Pattern**
- `RouteService` as facade
- Delegates to specialized services
- Backward compatibility layer

### **4. Singleton Pattern**
- Shared `QdrantVectorStore` instance
- Shared `EmbeddingGenerator` instance
- Global connection pools

### **5. Repository Pattern**
- `LocationInfoService` for data access
- Abstracts database queries
- Cache-aside pattern

---

## 🔍 Key Features

### **1. H3 Hexagonal Indexing**
- Fast spatial queries
- Uniform cell sizes
- Hierarchical structure
- Redis caching per cell

### **2. Vector Semantic Search**
- Multilingual E5 embeddings (384-dim)
- Cosine similarity matching
- Query-passage asymmetric encoding
- Support multiple queries

### **3. Greedy Route Building**
- O(n²) time complexity
- Combined scoring (distance + rating)
- Opening hours validation
- Time budget constraints

### **4. POI Replacement**
- Find similar alternatives
- Context-aware selection
- Distance + rating scoring
- Cache invalidation

### **5. Async Processing**
- ProcessPoolExecutor for CPU-bound tasks
- Parallel database queries
- Non-blocking cache operations

---

## 📈 Performance Characteristics

### **Spatial Search**
- **H3 Cache Hit:** < 50ms
- **H3 Cache Miss:** 100-200ms
- **PostGIS Fallback:** 200-500ms

### **Semantic Search**
- **Embedding Generation:** 20-50ms (single query)
- **Qdrant Vector Search:** 30-80ms (10k vectors)
- **Combined:** 50-150ms

### **Route Building**
- **Input Size:** 50-100 POIs
- **Routes:** 3-5 routes
- **Time:** 500ms - 2s (depends on target_places)
- **Process Pool:** Parallel execution

### **Cache Performance**
- **Redis Hit Rate:** 80-90% (production)
- **TTL:** 1 hour (configurable)
- **Route Cache Size:** ~5KB per route

---

## 🐛 Troubleshooting

### **Connection Issues**

#### Qdrant Connection Error
```bash
# Check if Qdrant is running
curl http://localhost:6333/collections

# Check Qdrant health
curl http://localhost:6333/healthz

# View Qdrant logs (Docker)
docker logs <qdrant_container_id>

# Restart Qdrant
docker restart <qdrant_container_id>
```

#### Redis Connection Error
```bash
# Test Redis connection
redis-cli ping
# Expected: PONG

# Check Redis info
redis-cli INFO

# Clear Redis cache (if needed)
redis-cli FLUSHDB
```

#### PostgreSQL Connection Error
```bash
# Test connection
psql -h localhost -U postgres -d location_db

# Check if PostGIS is enabled
psql -d location_db -c "SELECT PostGIS_version();"

# View active connections
psql -d location_db -c "SELECT * FROM pg_stat_activity;"
```

### **Performance Issues**

#### Slow Spatial Search
```python
# Check H3 cache hit rate
# Monitor Redis keys
redis-cli KEYS "h3:*" | wc -l

# Check PostgreSQL query performance
EXPLAIN ANALYZE SELECT * FROM poi_clean 
WHERE ST_DWithin(geometry, ST_SetSRID(ST_MakePoint(106.77, 10.83), 4326)::geography, 5000);
```

#### Slow Semantic Search
```python
# Check Qdrant collection info
curl http://localhost:6333/collections/poi_locations

# Check vector count
# Should match number of POIs in database

# Re-index if needed
python -m scripts.ingest_qdrant.ingest_all
```

### **Data Issues**

#### Missing POIs in Search Results
```bash
# Check if POI exists in database
psql -d location_db -c "SELECT * FROM poi_clean WHERE id = 'poi_id';"

# Check if POI exists in Qdrant
curl http://localhost:6333/collections/poi_locations/points/poi_id

# Re-ingest specific POI
curl -X POST "http://localhost:8000/api/v1/poi/update-poi-clean" \
  -H "Content-Type: application/json" \
  -d '{"add": ["poi_id"]}'
```

#### Opening Hours Validation Fails
```python
# Check open_hours format in database
SELECT id, open_hours FROM poi_clean WHERE id = 'poi_id';

# Expected format:
# {"Monday": "08:00-22:00", "Tuesday": "08:00-22:00", ...}

# Update opening hours
UPDATE poi_clean SET open_hours = '{"Monday": "08:00-22:00"}' WHERE id = 'poi_id';
```

### **Common Errors**

#### Error: "Vector dimension mismatch"
**Cause:** Embedding model changed but Qdrant collection not re-created

**Solution:**
```bash
# Delete collection
curl -X DELETE http://localhost:6333/collections/poi_locations

# Restart server (will auto-create collection)
python main.py

# Re-ingest data
python -m scripts.ingest_qdrant.ingest_all
```

#### Error: "Database pool not initialized"
**Cause:** Service used before startup event completed

**Solution:**
- Ensure server.py startup event completes
- Check logs for initialization errors
- Verify database connection string in .env

#### Error: "Route building timeout"
**Cause:** Too many POIs or complex routing

**Solution:**
```python
# Reduce top_k_semantic
{
  "semantic_query": "...",
  "top_k_semantic": 10  # Reduce from 20
}

# Reduce target_places
{
  "target_places": 4  # Reduce from 5
}

# Increase max_time_minutes
{
  "max_time_minutes": 240  # Increase from 180
}
```

---

## 🔧 Configuration Reference

### **Environment Variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_NAME` | location_db | Database name |
| `DB_USER` | postgres | Database user |
| `DB_PASSWORD` | - | Database password |
| `QDRANT_URL` | http://localhost:6333 | Qdrant server URL |
| `QDRANT_API_KEY` | - | Qdrant API key (optional) |
| `QDRANT_COLLECTION_NAME` | poi_locations | Collection name |
| `VECTOR_DIMENSION` | 384 | Embedding dimension |
| `REDIS_HOST` | localhost | Redis host |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_DB` | 0 | Redis database index |
| `REDIS_TTL` | 3600 | Cache TTL (seconds) |
| `H3_RESOLUTION` | 9 | H3 hexagon resolution |
| `EMBEDDING_MODEL` | intfloat/multilingual-e5-small | Embedding model |
| `OPENAI_API_KEY` | - | OpenAI API key |

### **Route Configuration**

Located in `radius_logic/route/route_config.py`:

```python
class RouteConfig:
    DEFAULT_STAY_TIME = 30  # minutes per POI
    
    # Speed by transportation mode (km/h)
    SPEEDS = {
        "WALKING": 5,
        "BICYCLING": 15,
        "TRANSIT": 20,
        "FLEXIBLE": 25,
        "DRIVING": 40
    }
    
    # Scoring weights
    SCORE_WEIGHT = 0.7
    DISTANCE_WEIGHT = 0.3
    
    # End POI constraints
    MAX_DISTANCE_RATIO = 0.2  # Must be within 20% of max distance
```

---

## 🚀 Deployment

### **Docker Deployment**

```dockerfile
# Build image
docker build -t location-api:latest .

# Run container
docker run -d \
  --name location-api \
  -p 8000:8000 \
  --env-file .env \
  --network host \
  location-api:latest
```

### **Docker Compose Production**

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=postgres
      - REDIS_HOST=redis
      - QDRANT_URL=http://qdrant:6333
    depends_on:
      - postgres
      - redis
      - qdrant
    restart: unless-stopped

  postgres:
    image: postgis/postgis:13-3.1
    environment:
      POSTGRES_DB: location_db
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:6-alpine
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

volumes:
  postgres_data:
  qdrant_data:
```

### **Production Considerations**

1. **Connection Pooling:**
   - PostgreSQL: min=10, max=50
   - Adjust based on load

2. **Redis:**
   - Enable persistence (AOF or RDB)
   - Set maxmemory policy

3. **Qdrant:**
   - Use persistent storage
   - Enable authentication
   - Scale horizontally if needed

4. **API:**
   - Use Gunicorn/Uvicorn workers
   - Enable CORS if needed
   - Add rate limiting
   - Implement authentication

5. **Monitoring:**
   - Log aggregation (ELK, Loki)
   - Metrics (Prometheus, Grafana)
   - APM (New Relic, DataDog)

---

## 📚 Additional Resources

### **Documentation**
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [H3 Documentation](https://h3geo.org/)
- [PostGIS Documentation](https://postgis.net/documentation/)

### **Related Projects**
- [Sentence Transformers](https://www.sbert.net/)
- [Asyncpg](https://magicstack.github.io/asyncpg/)
- [Redis-py](https://redis-py.readthedocs.io/)

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## 📝 License

This project is proprietary software developed by Kyanon Digital.

---

## 👥 Team

**Developed by Kyanon Digital**

For questions or support, contact the development team.

---

## 🔄 Version History

### **v1.0.0** (Current)
- ✅ Async architecture implementation
- ✅ H3 hexagonal indexing with Redis cache
- ✅ Qdrant vector search integration
- ✅ Greedy route building algorithm
- ✅ Opening hours validation
- ✅ POI replacement functionality
- ✅ Multi-query semantic search
- ✅ User preference tracking

### **Roadmap**
- 🔄 Machine learning route optimization
- 🔄 Real-time traffic integration
- 🔄 Multi-language support enhancement
- 🔄 Mobile app integration
- 🔄 Advanced caching strategies
- 🔄 GraphQL API support
