from sentence_transformers import SentenceTransformer
from config.config import Config
import numpy as np
from typing import List, Union
import time
import torch
import os

# Force offline mode for HuggingFace to use cached models
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

class EmbeddingGenerator:
    """Handles text embedding generation using local embedding model"""
    
    def __init__(self):
        """Initialize the embedding generator with local model"""
        print(f"Loading embedding model: {Config.EMBEDDING_MODEL}")
        
        # Set device
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"Using device: {self.device}")
        
        try:
            # Load model from cache (offline mode is set globally)
            self.model = SentenceTransformer(
                Config.EMBEDDING_MODEL, 
                device=self.device
            )
            print(f"✓ Model loaded from cache! Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            print(f"💡 Model may not be cached yet. Please run once with internet to download:")
            print(f"   python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('{Config.EMBEDDING_MODEL}')\"")
            raise
    
    def generate_single_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text (optimized for query)
        
        Args:
            text: Input text string
            
        Returns:
            numpy array of single embedding
        """
        try:
            # Use "query:" prefix for queries (E5 model recommendation)
            processed_text = f"query: {text}"
            
            embedding = self.model.encode(
                processed_text,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            
            return embedding
            
        except Exception as e:
            print(f"Error generating single embedding: {e}")
            raise