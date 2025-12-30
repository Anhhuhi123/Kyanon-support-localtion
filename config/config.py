import os
from dotenv import load_dotenv
from typing import Dict
from enum import Enum

# Load environment variables from .env file
load_dotenv()


class TransportationMode(str, Enum):
    """Enum cho các phương tiện di chuyển"""
    WALKING = "WALKING"
    BICYCLING = "BICYCLING"
    TRANSIT = "TRANSIT"
    FLEXIBLE = "FLEXIBLE"
    DRIVING = "DRIVING"


class Config:
    """Cấu hình tổng hợp cho toàn bộ ứng dụng"""
    
    # Database Configuration
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "demo_p3")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    
    # Document Processing Configuration
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
    
    # Embedding Model Configuration
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    
    # Qdrant configurations
    USE_QDRANT = True  # Use Qdrant for vector storage
    QDRANT_COLLECTION_NAME = "Map_Kyanon"  # Lưu trữ trong Qdrant
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
    VECTOR_DIMENSION = int(os.getenv("VECTOR_DIMENSION", "1024"))  # E5-large: 1024, E5-base: 768
    
    # Location Search Configuration
    TOP_K_RESULTS = 10  # Số lượng điểm gần nhất trả về
    
    # Transportation Mode Radius Configuration
    # Cấu hình bán kính tìm kiếm cho từng phương tiện di chuyển
    TRANSPORTATION_CONFIG: Dict[str, Dict[str, int]] = {
        TransportationMode.WALKING: {
            "min_radius": 0,      # 500m
            "max_radius": 5000,     # 5000m (5km) - tăng để tìm đủ 50 địa điểm
            "step": 500              # Tăng 500m mỗi lần
        },
        TransportationMode.BICYCLING: {
            "min_radius": 0,     # 2000m (2km)
            "max_radius": 15000,     # 15000m (15km)
            "step": 5000             # Tăng 1000m mỗi lần (was 5m)
        },
        TransportationMode.TRANSIT: {
            "min_radius": 0,     # 2000m (2km)
            "max_radius": 30000,    # 20000m (20km)
            "step": 10000             # Tăng 4000m mỗi lần (was 10m)
        },
        TransportationMode.FLEXIBLE: {
            "min_radius": 0,     # 2000m (2km)
            "max_radius": 20000,    # 20000m (20km)
            "step": 5000             # Tăng 5000m mỗi lần (was 10m)
        },
        TransportationMode.DRIVING: {
            "min_radius": 0,     # 2000m (2km)
            "max_radius": 30000,    # 30000m (30km)
            "step": 10000             # Tăng 5000m mỗi lần (was 10m)
        }
    }
    
    @classmethod
    def get_db_connection_string(cls) -> str:
        """
        Generate PostgreSQL connection string
        
        Returns:
            Connection string format: "host=... port=... dbname=... user=... password=..."
        """
        return f"host={cls.DB_HOST} port={cls.DB_PORT} dbname={cls.DB_NAME} user={cls.DB_USER} password={cls.DB_PASSWORD}"
    
    @classmethod
    def get_transportation_config(cls, mode: str) -> Dict[str, int]:
        """
        Lấy cấu hình cho một phương tiện cụ thể
        
        Args:
            mode: Phương tiện di chuyển (WALKING, BICYCLING, etc.)
            
        Returns:
            Dict chứa min_radius, max_radius, step
            
        Raises:
            ValueError: Nếu mode không hợp lệ
        """
        mode_upper = mode.upper()
        if mode_upper not in cls.TRANSPORTATION_CONFIG:
            raise ValueError(
                f"Invalid transportation mode: {mode}. "
                f"Valid modes: {list(cls.TRANSPORTATION_CONFIG.keys())}"
            )
        return cls.TRANSPORTATION_CONFIG[mode_upper]
    
    @classmethod
    def validate_transportation_mode(cls, mode: str) -> bool:
        """Kiểm tra mode có hợp lệ không"""
        return mode.upper() in cls.TRANSPORTATION_CONFIG
    
    @classmethod
    def validate(cls):
        """Validate that all required configurations are set"""
        # Only validate Qdrant credentials (LLM key optional for embedding-only tasks)
        if cls.USE_QDRANT and not cls.QDRANT_API_KEY:
            raise ValueError("QDRANT_API_KEY not found in environment variables")
        if cls.USE_QDRANT and not cls.QDRANT_URL:
            raise ValueError("QDRANT_URL not found in environment variables")
        if cls.USE_QDRANT and not cls.QDRANT_URL.startswith("http"):
            raise ValueError("QDRANT_URL must be a valid URL starting with http/https")
        # Validate database configuration
        if not cls.DB_HOST:
            raise ValueError("DB_HOST not found in environment variables")
        if not cls.DB_NAME:
            raise ValueError("DB_NAME not found in environment variables")
        if not cls.DB_USER:
            raise ValueError("DB_USER not found in environment variables")
        return True