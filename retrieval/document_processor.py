import re
from typing import List
from config.config import Config

def load_text_file(file_path: str) -> List[str]:
    """
    Load text from a txt file and split into lines
    
    Args:
        file_path: Path to the txt file
        
    Returns:
        List of place lines only (lines with number. PlaceName : count format)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Filter lines: only keep lines with format "number. PlaceName : count địa điểm"
        filtered_lines = []
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Only keep lines that match pattern: number. text : number địa điểm
            # Example: "  1. Coffee shop                                        :  158 địa điểm"
            if re.match(r'^\s*\d+\.\s+.+:\s+\d+\s+địa điểm', line):
                filtered_lines.append(line)
        
        print(f"✓ Loaded {len(filtered_lines)} place entries from {file_path}")
        return filtered_lines
        
    except Exception as e:
        print(f"Error loading text file: {e}")
        raise

class DocumentProcessor:
    """Handles simple text chunking for txt files"""
    
    def __init__(self, chunk_size: int = Config.CHUNK_SIZE, chunk_overlap: int = Config.CHUNK_OVERLAP):
        """
        Initialize document processor
        
        Args:
            chunk_size: Maximum size of each chunk (in characters)
            chunk_overlap: Overlap between consecutive chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text
        
        Args:
            text: Raw text to clean
            
        Returns:
            Cleaned text
        """
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks by characters
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        # Clean the text first
        text = self.clean_text(text)
        
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Get chunk from start to start + chunk_size
            end = start + self.chunk_size
            chunk = text[start:end]
            
            chunks.append(chunk.strip())
            
            # Move forward by (chunk_size - overlap)
            start += (self.chunk_size - self.chunk_overlap)
        
        # Remove empty chunks
        chunks = [chunk for chunk in chunks if chunk.strip()]
        
        return chunks

    
    