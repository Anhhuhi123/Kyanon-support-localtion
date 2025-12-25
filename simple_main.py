#!/usr/bin/env python3
"""
Simple Main - Text Embedding & Search for txt files
"""
import argparse
from retrieval.document_processor import load_text_file, DocumentProcessor
from retrieval.embeddings import EmbeddingGenerator
from retrieval.qdrant_vector_store import QdrantVectorStore
from config.config import Config

def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(description="Simple RAG Pipeline for Text Files")
    parser.add_argument("--ingest", type=str, help="Ingest text from file (e.g., danh_sach_dia_diem.txt)")
    parser.add_argument("--query", type=str, help="Search for similar text")
    parser.add_argument("--stats", action="store_true", help="Show vector store statistics")
    parser.add_argument("--reset", action="store_true", help="Reset the vector store")
    
    args = parser.parse_args()
    
    # Validate config
    Config.validate()
    
    # Initialize components
    processor = DocumentProcessor()
    embedder = EmbeddingGenerator()
    vector_store = QdrantVectorStore()
    
    if args.reset:
        print("Resetting vector store...")
        vector_store.delete_collection()
        vector_store._initialize_client()
        print("✓ Vector store reset completed!")
        return
    
    if args.ingest:
        print(f"📄 Ingesting text from: {args.ingest}")
        
        try:
            # Load text lines
            lines = load_text_file(args.ingest)
            print(f"✓ Loaded {len(lines)} lines")
            
            # Chunk all lines
            all_chunks = []
            for line in lines:
                chunks = processor.chunk_text(line)
                all_chunks.extend(chunks)
            
            print(f"✓ Created {len(all_chunks)} chunks")
            
            # Generate embeddings
            print("🔄 Generating embeddings...")
            embeddings = embedder.generate_embeddings(all_chunks)
            print(f"✓ Generated {len(embeddings)} embeddings")
            
            # Store in Qdrant
            print("🔄 Storing embeddings in Qdrant...")
            vector_store.add_embeddings(embeddings, all_chunks)
            print("✓ Ingestion completed!")
            
            # Show stats
            stats = vector_store.get_stats()
            print(f"\n📊 Stats:")
            print(f"  Total embeddings: {stats['total_embeddings']}")
            print(f"  Dimension: {stats['dimension']}")
            print(f"  Backend: {stats['backend']}")
            
        except Exception as e:
            print(f"❌ Error during ingestion: {e}")
            import traceback
            traceback.print_exc()
        return
    
    if args.stats:
        stats = vector_store.get_stats()
        print("📊 Vector Store Statistics:")
        print(f"  Total embeddings: {stats['total_embeddings']}")
        print(f"  Dimension: {stats['dimension']}")
        print(f"  Backend: {stats['backend']}")
        print(f"  Collection: {stats['collection_name']}")
        return
    
    if args.query:
        print(f"🔍 Query: {args.query}")
        
        # Check if index has data
        stats = vector_store.get_stats()
        if stats['total_embeddings'] == 0:
            print("❌ No embeddings found. Please run --ingest first.")
            return
        
        try:
            # Generate query embedding
            query_embedding = embedder.generate_single_embedding(args.query)
            
            # Search
            similar_texts, scores = vector_store.search(query_embedding, k=Config.TOP_K_RESULTS)
            
            print(f"\n📊 Found {len(similar_texts)} similar results:")
            print("-" * 80)
            for i, (text, score) in enumerate(zip(similar_texts, scores), 1):
                print(f"\n{i}. Score: {score:.3f}")
                print(f"   {text[:200]}..." if len(text) > 200 else f"   {text}")
            print("-" * 80)
            
        except Exception as e:
            print(f"❌ Error during search: {e}")
            import traceback
            traceback.print_exc()
        return
    
    # Interactive mode
    print("=" * 80)
    print("🔍 Simple RAG Pipeline - Interactive Search")
    print("=" * 80)
    print("Commands:")
    print("  stats   - Show vector store statistics")
    print("  reset   - Reset vector store")
    print("  quit    - Exit")
    print("Or just type your search query!")
    print("-" * 80)
    
    # Check if index has data
    stats = vector_store.get_stats()
    if stats['total_embeddings'] == 0:
        print("⚠️  No embeddings found. Please run with --ingest first:")
        print("   python simple_main.py --ingest danh_sach_dia_diem.txt")
        return
    
    print(f"✓ Ready to search ({stats['total_embeddings']} embeddings loaded)")
    
    while True:
        try:
            user_input = input("\n🔍 > ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if user_input.lower() == 'stats':
                stats = vector_store.get_stats()
                print(f"Total embeddings: {stats['total_embeddings']}")
                print(f"Dimension: {stats['dimension']}")
                continue
            
            if user_input.lower() == 'reset':
                vector_store.delete_collection()
                vector_store._initialize_client()
                print("✓ Vector store reset!")
                continue
            
            if not user_input:
                continue
            
            # Search
            query_embedding = embedder.generate_single_embedding(user_input)
            similar_texts, scores = vector_store.search(query_embedding, k=Config.TOP_K_RESULTS)
            
            print(f"\n📊 Found {len(similar_texts)} results:")
            print("-" * 80)
            for i, (text, score) in enumerate(zip(similar_texts, scores), 1):
                print(f"\n{i}. Score: {score:.3f}")
                print(f"   {text[:200]}..." if len(text) > 200 else f"   {text}")
            print("-" * 80)
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
