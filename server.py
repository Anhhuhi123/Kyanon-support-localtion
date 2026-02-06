import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from fastapi import FastAPI
from qdrant_client import AsyncQdrantClient
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

# Health check endpoint với kiểm tra dependencies (ASYNC)
@app.get("/health", tags=["Health"])
async def health_check():
    health_status = {
        "status": "healthy",
        "service": "Location Search API",
        "checks": {}
    }
    
    # Check Redis (async pool)
    try:
        redis_client = get_redis_client()
        if redis_client is None:
            raise RuntimeError("Redis client not initialized")
        await redis_client.ping()
        health_status["checks"]["redis"] = "healthy"
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Database (async pool)
    try:
        db_pool = get_db_pool()
        if db_pool is None:
            raise RuntimeError("Database pool not initialized")
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Qdrant (async client)
    try:
        # Sử dụng async client từ vector_store trong route service
        if route_api_module._route_service_instance is not None:
            vector_store = route_api_module._route_service_instance.base_service.vector_store
            if vector_store and vector_store.client:
                await vector_store.client.get_collections()
            else:
                raise RuntimeError("Vector store or client not initialized")
        else:
            raise RuntimeError("Route service not initialized")
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
    
    # 2. Initialize AsyncQdrantClient và QdrantVectorStore
    from retrieval.qdrant_vector_store import QdrantVectorStore
    from retrieval.embeddings import EmbeddingGenerator
    from services.route_service import RouteService
    from services.location_search import LocationSearch
    from services.poi_service import PoiService
    from services.cache_search import CacheSearch


    # Lấy pools từ config
    db_pool = get_db_pool()
    redis_client = get_redis_client()

    # Set cache service singleton cho route API
    route_api_module._cache_service = CacheSearch(redis_client)
    
    # 3. Khởi tạo AsyncQdrantClient
    async_qdrant = AsyncQdrantClient(
        url=Config.QDRANT_URL,
        api_key=Config.QDRANT_API_KEY if Config.QDRANT_API_KEY else None
    )
    
    # 4. Khởi tạo EmbeddingGenerator (shared singleton)
    embedder = EmbeddingGenerator()
    
    # 5. Khởi tạo QdrantVectorStore với AsyncQdrantClient, db_pool và embedder
    vector_store = QdrantVectorStore(
        client=async_qdrant,
        db_pool=db_pool,
        embedder=embedder
    )
    await vector_store.initialize_async()
    
    # 6. Khởi tạo services với async resources + shared vector_store & embedder
    route_api_module._route_service_instance = RouteService(
        db_pool=db_pool,
        redis_client=redis_client,
        vector_store=vector_store,
        embedder=embedder
    )
    
    # Update location service với async resources
    location_api_module.location_search = LocationSearch(
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    # Initialize POI service với async resources
    poi_api_module.poi_service = PoiService(
        db_pool=db_pool,
        redis_client=redis_client
    )
    
    # Set qdrant_vector_store cho POI API (dùng chung với route service)
    poi_api_module.qdrant_vector_store = vector_store
    
    # Set search_service cho POI API (dùng chung với route service)
    poi_api_module.search_service = route_api_module._route_service_instance
    
    print("=" * 60)
    print("✅ All async services initialized and ready!")
    print("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    """Close async resources khi server shutdown"""
    print("🛑 Shutting down async resources...")
    
    # Close AsyncQdrantClient từ vector_store
    if route_api_module._route_service_instance is not None:
        vector_store = route_api_module._route_service_instance.base_service.vector_store
        if vector_store and vector_store.client:
            await vector_store.client.close()
            print("✅ Qdrant client closed")
    
    await close_db_pool()
    await close_redis_client()
    print("✅ Async resources closed")

# Include routers
app.include_router(location_router)
app.include_router(semantic_router)
app.include_router(poi_router)