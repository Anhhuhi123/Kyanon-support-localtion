import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for RAG pipeline"""
    
    # API Keys
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    QDRANT_URL = os.getenv("QDRANT_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    
    # Model configurations
    LLM_MODEL = "gemini-2.5-flash"
    EMBEDDING_MODEL = "intfloat/multilingual-e5-small"  # Local embedding model (384 dimensions)
    VECTOR_DIMENSION = 384  # Dimension of embedding vectors
    EMBEDDING_BATCH_SIZE = 32  # Batch size for local model (adjust based on your GPU/CPU)
    EMBEDDING_DELAY = 0  # No delay needed for local model
    
    # LLM Rate limiting (Gemini Free Tier: 10 requests/minute)
    LLM_REQUESTS_PER_MINUTE = 9  # Stay under 10 to be safe
    LLM_DELAY_BETWEEN_REQUESTS = 7  # Delay in seconds (60/9 ≈ 6.7s)
    
    # RAG configurations
    CHUNK_SIZE = 200
    CHUNK_OVERLAP = 50
    TOP_K_RESULTS = 10  # Legacy parameter (không dùng nếu có reranking)
    
    # Qdrant configurations 
    USE_QDRANT = True  # Use Qdrant for vector storage
    QDRANT_COLLECTION_NAME = "Map_Kyanon" # Lưu trữ trong Qdrant
    
    @classmethod
    def validate(cls):
        """Validate that all required configurations are set"""
        # Only validate Qdrant credentials (LLM key optional for embedding-only tasks)
        if cls.USE_QDRANT and not cls.QDRANT_API_KEY:
            raise ValueError("QDRANT_API_KEY not found in environment variables")
        if cls.USE_QDRANT and not cls.QDRANT_URL:
            raise ValueError("QDRANT_URL not found in environment variables")
        return True

# Dùng tech gì cost, server 
# Thêm data vào kho tri thức 
# build 1 server để gọi api qua 
# Ước lượng thời gian 
# vẽ thuật toán xử lý 