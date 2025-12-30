"""
Main API Server
Kết hợp tất cả các API endpoints
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from fastapi import FastAPI
from config.config import Config

# Import routers
from Router.v1.location_api import router as location_router
from Router.v1.semantic_api import router as semantic_router

# Validate config
Config.validate()

# Initialize FastAPI app
app = FastAPI(
    title="Location Search API",
    description="API tìm kiếm địa điểm gần nhất theo tọa độ và phương tiện di chuyển, kết hợp với tìm kiếm ngữ nghĩa",
    version="1.0.0"
)

# Include routers
app.include_router(location_router)
app.include_router(semantic_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Location Search API",
        "version": "1.0.0",
        "endpoints": {
            "spatial_search": "/api/v1/locations/search",
            "semantic_search": "/api/v1/semantic/search",
            "combined_search": "/api/v1/semantic/combined",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Location Search API"
    }