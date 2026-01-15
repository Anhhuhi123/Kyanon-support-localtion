import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from fastapi import FastAPI
import redis
import psycopg2
from qdrant_client import QdrantClient
from config.config import Config
from config.db import (
    init_db_pool,
    init_redis_client,
    get_db_pool,
    get_redis_client,
    close_db_pool,
    close_redis_client,
)

# Routers as modules (we need module objects to set service instances on startup)
import routers.v1.route_api as route_api_module
import routers.v1.location_api as location_api_module
import routers.v1.poi_api as poi_api_module

# Expose router objects for app.include_router below
location_router = location_api_module.router
semantic_router = route_api_module.router
poi_router = poi_api_module.router

# Validate config
Config.validate()

# Initialize FastAPI app
app = FastAPI(
    title="Location Search API",
    description="API tìm kiếm địa điểm gần nhất theo tọa độ và phương tiện di chuyển, kết hợp với tìm kiếm ngữ nghĩa",
    version="1.0.0"
)

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Location Search API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

# Health check endpoint với kiểm tra dependencies
@app.get("/health", tags=["Health"])
async def health_check():
    health_status = {
        "status": "healthy",
        "service": "Location Search API",
        "checks": {}
    }
    
    # Check Redis
    try:
        redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            socket_connect_timeout=2
        )
        redis_client.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Database
    try:
        conn = psycopg2.connect(Config.get_db_connection_string())
        conn.close()
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Qdrant
    try:
        qdrant_client = QdrantClient(
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY if Config.QDRANT_API_KEY else None
        )
        qdrant_client.get_collections()
        health_status["checks"]["qdrant"] = "healthy"
    except Exception as e:
        health_status["checks"]["qdrant"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    return health_status

# Startup event: initialize async resources
@app.on_event("startup") 
async def startup_event():
    """
    Khởi tạo async resources khi server startup:
    - Async PostgreSQL connection pool
    - Async Redis client
    - Qdrant client và embedding model
    """
    print("=" * 60)
    print("🚀 Starting async initialization...")
    print("=" * 60)
    
    # 1. Initialize async database pool và Redis client
    await init_db_pool()
    await init_redis_client()
    
    # 2. Initialize semantic search service (Qdrant + Embedding Model)
    from services.route_service import SemanticSearchService
    from services.location_service import LocationService

    # Lấy pools từ config
    db_pool = get_db_pool()
    redis_client = get_redis_client()
    
    # Khởi tạo services với async resources
    route_api_module._route_service_instance = SemanticSearchService(
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    # Update location service với async resources
    location_api_module.location_service = LocationService(
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    print("=" * 60)
    print("✅ All async services initialized and ready!")
    print("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    """Close async resources khi server shutdown"""
    print("🛑 Shutting down async resources...")
    await close_db_pool()
    await close_redis_client()
    print("✅ Async resources closed")

# Include routers
app.include_router(location_router)
app.include_router(semantic_router)
app.include_router(poi_router)