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
from routers.v1.poi_api import router as poi_router
# Validate config
Config.validate()
# Initialize FastAPI app
app = FastAPI(
    title="Location Search API",
    description="API tìm kiếm địa điểm gần nhất theo tọa độ và phương tiện di chuyển, kết hợp với tìm kiếm ngữ nghĩa",
    version="1.0.0"
)
# Startup event: singleton pattern
# @app.on_event("startup") 
# async def startup_event():
#     """
#     Khởi tạo services khi server startup để:
#     - Giữ kết nối Qdrant
#     - Load model 1 lần duy nhất
#     - Tăng tốc độ response
#     """
#     print("Initializing services...")
#     # Import ở đây để đảm bảo chỉ init 1 lần
#     from services.semantic_search_service import SemanticSearchService
#     import routers.v1.semantic_api as semantic_api_module
    
#     # Khởi tạo service (sẽ connect Qdrant và load model)
#     semantic_api_module._semantic_service_instance = SemanticSearchService()
#     print("Services initialized and ready!")

# Include routers
app.include_router(location_router)
app.include_router(semantic_router)
app.include_router(poi_router)