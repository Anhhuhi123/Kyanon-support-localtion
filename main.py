"""
Main Entry Point
Chạy Location Search API Server
"""
import uvicorn

if __name__ == "__main__":
    print("🚀 Starting Location Search API...")
    print("📖 API Documentation: http://localhost:8000/docs")
    # print("🔍 Search endpoint: http://localhost:8000/api/v1/locations/search")
    print("-" * 60)
    
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
