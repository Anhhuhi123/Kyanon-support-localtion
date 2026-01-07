"""
Main API Server
Kết hợp tất cả các API endpoints
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from fastapi import FastAPI
from config.config import Config
from routers.v1.location_api import router as location_router
from routers.v1.semantic_api import router as semantic_router

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
    """
    Root endpoint - Trả về thông tin về API
    """
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
    """
    Health check endpoint để kiểm tra trạng thái của API và các dependencies
    """
    health_status = {
        "status": "healthy",
        "service": "Location Search API",
        "checks": {}
    }
    
    # Check Redis
    try:
        import redis
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
        import psycopg2
        conn = psycopg2.connect(Config.get_db_connection_string())
        conn.close()
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Qdrant
    try:
        from qdrant_client import QdrantClient
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

# Startup event: singleton pattern
@app.on_event("startup") 
async def startup_event():
    """
    Khởi tạo services khi server startup để:
    - Giữ kết nối Qdrant
    - Load model 1 lần duy nhất
    - Tăng tốc độ response
    """
    print("Initializing services...")
    # Import ở đây để đảm bảo chỉ init 1 lần
    from services.semantic_search_service import SemanticSearchService
    import routers.v1.semantic_api as semantic_api_module
    
    # Khởi tạo service (sẽ connect Qdrant và load model)
    semantic_api_module._semantic_service_instance = SemanticSearchService()
    print("Services initialized and ready!")

# Include routers
app.include_router(location_router)
app.include_router(semantic_router)