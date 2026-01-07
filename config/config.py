import os
from enum import Enum
from typing import Dict
from dotenv import load_dotenv

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
    
    # Redis Configuration (for H3 caching)
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "3600"))  # 1 hour default
    
    # H3 Hexagonal Indexing Configuration
    H3_RESOLUTION = int(os.getenv("H3_RESOLUTION", "9"))  # Resolution 9: ~461m diameter per hexagon
    # Resolution options:
    # - 8: ~1.22km diameter (fewer cells)
    # - 9: ~461m diameter (balanced) ✅
    # - 10: ~174m diameter (more precision)
    
    # Location Search Configuration
    TOP_K_RESULTS = 10  # Số lượng điểm gần nhất trả về
    
    # Transportation Mode Configuration
    # H3 k-ring coverage (resolution 9, edge ~174m):
    # k=5: ~1.4km (91 cells), k=10: ~2.9km (331 cells), k=15: ~4.3km (721 cells)
    # k=20: ~5.8km (1261 cells), k=30: ~8.6km (2791 cells), k=40: ~11.5km (4921 cells)
    TRANSPORTATION_CONFIG: Dict[str, Dict[str, int]] = {
        TransportationMode.WALKING: {
            "h3_k_ring": 15         # k=15: ~4.3km coverage (721 cells)
        },
        TransportationMode.BICYCLING: {
            "h3_k_ring": 30          # k=30: ~8.6km coverage (2791 cells)
        },
        TransportationMode.TRANSIT: {
            "h3_k_ring": 40          # k=40: ~11.5km coverage (4921 cells)
        },
        TransportationMode.FLEXIBLE: {
            "h3_k_ring": 60          # k=60: ~17.2km coverage (10981 cells)
        },
        TransportationMode.DRIVING: {
            "h3_k_ring": 100         # k=100: ~28.7km coverage (30301 cells)
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
            Dict chứa h3_k_ring (H3 k-ring value cho mode)
            
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