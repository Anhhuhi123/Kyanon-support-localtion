"""
Script để ingest POI data từ PostgreSQL vào Qdrant
- Lấy id và poi_type từ database
- Tạo embeddings từ poi_type
- Lưu vào Qdrant với point.id = location id, payload chỉ chứa poi_type
"""
import sys
import os
# Add parent directory to path để import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct 
from retrieval.embeddings import EmbeddingGenerator
from config.config import Config

def fetch_poi_data_from_db():
    """
    Lấy id và poi_type từ database
    
    Returns:
        List[Tuple]: [(id, poi_type), ...]
    """
    print("🔍 Kết nối database...")
    conn = psycopg2.connect(Config.get_db_connection_string())
    cursor = conn.cursor()
    
    # Query để lấy id và poi_type
    query = """
        SELECT id, poi_type_clean 
        FROM public."PoiClean" 
        WHERE poi_type_clean IS NOT NULL AND poi_type_clean != ''
        ORDER BY id
    """
    
    print("📊 Đang query dữ liệu từ database...")
    cursor.execute(query)
    results = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    print(f"✓ Đã lấy {len(results)} địa điểm từ database")
    return results

def reset_qdrant_collection(client: QdrantClient, collection_name: str, dimension: int):
    """
    Xóa và tạo lại collection trong Qdrant
    
    Args:
        client: Qdrant client instance
        collection_name: Tên collection
        dimension: Số chiều của vector embeddings
    """
    print(f"🔄 Reset collection '{collection_name}'...")
    
    # Xóa collection cũ nếu tồn tại
    try:
        client.delete_collection(collection_name=collection_name)
        print(f"  ✓ Đã xóa collection cũ")
    except Exception as e:
        print(f"  ℹ️  Collection chưa tồn tại: {e}")
    
    # Tạo collection mới
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=dimension,
            distance=Distance.COSINE
        )
    )
    print(f"  ✓ Đã tạo collection mới với dimension {dimension}")

def ingest_to_qdrant(poi_data, embedder, client, collection_name, batch_size=100):
    """
    Ingest POI data vào Qdrant
    
    Args:
        poi_data: List[(id, poi_type)]
        embedder: EmbeddingGenerator instance
        client: Qdrant client
        collection_name: Tên collection
        batch_size: Số lượng points mỗi batch
    """
    print(f"\n📦 Bắt đầu ingest {len(poi_data)} địa điểm vào Qdrant...")
    
    # Tạo embeddings cho tất cả poi_type
    print("🔄 Tạo embeddings cho poi_type...")
    poi_types = [poi[1] for poi in poi_data]
    embeddings = embedder.generate_embeddings(poi_types)
    print(f"  ✓ Đã tạo {len(embeddings)} embeddings")
    
    # Chuẩn bị points
    print("🔄 Chuẩn bị points...")
    points = []
    for idx, (location_id, poi_type) in enumerate(poi_data):
        point = PointStruct(
            id=str(location_id),  # Chuyển sang string nếu cần
            vector=embeddings[idx].tolist(),
            payload={
                "poi_type_clean": poi_type
            }
        )
        points.append(point)
    
    # Upsert theo batch
    print(f"🚀 Upsert {len(points)} points vào Qdrant (batch size: {batch_size})...")
    total_batches = (len(points) + batch_size - 1) // batch_size
    
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(
            collection_name=collection_name,
            points=batch
        )
        batch_num = i // batch_size + 1
        print(f"  ✓ Batch {batch_num}/{total_batches}: upserted {len(batch)} points")
    
    print(f"✅ Hoàn thành upsert!")

def verify_collection(client: QdrantClient, collection_name: str):
    """
    Verify collection sau khi ingest
    
    Args:
        client: Qdrant client
        collection_name: Tên collection
    """
    print(f"\n🔍 Verify collection '{collection_name}'...")
    
    # Lấy thông tin collection
    collection_info = client.get_collection(collection_name=collection_name)
    print(f"  ✓ Tổng số points: {collection_info.points_count}")
    print(f"  ✓ Vector dimension: {collection_info.config.params.vectors.size}")
    print(f"  ✓ Distance metric: {collection_info.config.params.vectors.distance}")
    
    # Lấy 1 sample point
    sample = client.scroll(
        collection_name=collection_name,
        limit=1,
        with_payload=True,
        with_vectors=False
    )
    
    if sample[0]:
        point = sample[0][0]
        print(f"\n📋 Sample point:")
        print(f"  • point.id: {point.id}")
        print(f"  • payload: {point.payload}")

def main():
    """Main function để chạy toàn bộ workflow"""
    print("="*80)
    print("INGEST POI DATA VÀO QDRANT")
    print("="*80)
    
    try:
        # 1. Validate config
        print("\n1️⃣  Validate configuration...")
        Config.validate()
        print(f"  ✓ Database: {Config.DB_NAME}")
        print(f"  ✓ Qdrant URL: {Config.QDRANT_URL}")
        print(f"  ✓ Collection: {Config.QDRANT_COLLECTION_NAME}")
        
        # 2. Fetch data từ database
        print("\n2️⃣  Fetch data từ database...")
        poi_data = fetch_poi_data_from_db()
        
        if not poi_data:
            print("❌ Không có dữ liệu để ingest!")
            return
        
        # 3. Khởi tạo EmbeddingGenerator
        print("\n3️⃣  Khởi tạo EmbeddingGenerator...")
        embedder = EmbeddingGenerator()
        embedding_dim = embedder.model.get_sentence_embedding_dimension()
        print(f"  ✓ Model: {Config.EMBEDDING_MODEL}")
        print(f"  ✓ Dimension: {embedding_dim}")
        
        # 4. Kết nối Qdrant
        print("\n4️⃣  Kết nối Qdrant...")
        client = QdrantClient(
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY,
            timeout=60
        )
        print(f"  ✓ Đã kết nối Qdrant")
        
        # 5. Reset collection
        print("\n5️⃣  Reset collection...")
        reset_qdrant_collection(
            client=client,
            collection_name=Config.QDRANT_COLLECTION_NAME,
            dimension=embedding_dim
        )
        
        # 6. Ingest data
        print("\n6️⃣  Ingest data...")
        ingest_to_qdrant(
            poi_data=poi_data,
            embedder=embedder,
            client=client,
            collection_name=Config.QDRANT_COLLECTION_NAME,
            batch_size=100
        )
        
        # 7. Verify
        print("\n7️⃣  Verify collection...")
        verify_collection(client, Config.QDRANT_COLLECTION_NAME)
        
        print("\n" + "="*80)
        print("✅ HOÀN THÀNH INGEST DATA VÀO QDRANT!")
        print("="*80)
        print(f"\n📌 Lưu ý:")
        print(f"  • point.id = location id từ database")
        print(f"  • payload chỉ chứa: poi_type")
        print(f"  • Để lấy thông tin đầy đủ location, query lại database bằng point.id")
        
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
