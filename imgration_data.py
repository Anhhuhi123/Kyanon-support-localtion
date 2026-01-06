# import csv
# import psycopg2
# from psycopg2.extras import execute_batch
# from config.config import Config

# def create_table(conn):
#     """Tạo bảng nếu chưa tồn tại với cột geometry"""
#     cursor = conn.cursor()
    
#     # Kiểm tra và tạo PostGIS extension
#     cursor.execute("""
#         CREATE EXTENSION IF NOT EXISTS postgis;
#     """)
    
#     # Tạo bảng với geometry point
#     cursor.execute("""
#         CREATE TABLE IF NOT EXISTS poi_locations_uuid (
#             id UUID PRIMARY KEY,
#             name TEXT,
#             address TEXT,
#             lat DOUBLE PRECISION NOT NULL,
#             long DOUBLE PRECISION NOT NULL,
#             geom GEOMETRY(Point, 4326),
#             poi_type TEXT,
#             avg_star DOUBLE PRECISION,
#             total_reviews DOUBLE PRECISION,
#             normalize_stars_reviews DOUBLE PRECISION
#         );
#     """)
    
#     # Tạo spatial index cho cột geometry
#     cursor.execute("""
#         CREATE INDEX IF NOT EXISTS poi_locations_geom_idx 
#         ON poi_locations_uuid USING GIST(geom);
#     """)
    
#     # Thêm các cột mới nếu chưa tồn tại
#     cursor.execute("""
#         DO $$ 
#         BEGIN
#             -- Thêm cột avg_star nếu chưa có
#             IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
#                           WHERE table_name='poi_locations_uuid' AND column_name='avg_star') THEN
#                 ALTER TABLE poi_locations_uuid ADD COLUMN avg_star DOUBLE PRECISION;
#             END IF;
            
#             -- Thêm cột total_reviews nếu chưa có
#             IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
#                           WHERE table_name='poi_locations_uuid' AND column_name='total_reviews') THEN
#                 ALTER TABLE poi_locations_uuid ADD COLUMN total_reviews DOUBLE PRECISION;
#             END IF;
            
#             -- Thêm cột normalize_stars_reviews nếu chưa có
#             IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
#                           WHERE table_name='poi_locations_uuid' AND column_name='normalize_stars_reviews') THEN
#                 ALTER TABLE poi_locations_uuid ADD COLUMN normalize_stars_reviews DOUBLE PRECISION;
#             END IF;
#         END $$;
#     """)
    
#     conn.commit()
#     cursor.close()
#     print("✓ Tạo bảng và index thành công")
#     print("✓ Đã thêm/kiểm tra các cột: avg_star, total_reviews, normalize_stars_reviews")

# def import_csv_to_postgres(csv_file_path, batch_size=100):
#     """
#     Import dữ liệu từ CSV vào PostgreSQL với geometry
    
#     Args:
#         csv_file_path: Đường dẫn đến file CSV
#         batch_size: Số lượng records insert mỗi lần (default: 100)
#     """
#     # Kết nối database
#     conn = psycopg2.connect(Config.get_db_connection_string())
    
#     try:
#         # Tạo bảng
#         create_table(conn)
        
#         # Đọc và insert dữ liệu
#         cursor = conn.cursor()
        
#         with open(csv_file_path, 'r', encoding='utf-8-sig') as file:
#             csv_reader = csv.DictReader(file)
            
#             # Chuẩn bị dữ liệu cho batch insert
#             batch_data = []
#             total_rows = 0
#             skipped_rows = 0
            
#             for row in csv_reader:
#                 try:
#                     # Validate dữ liệu
#                     if not row['id'] or not row['lat'] or not row['long']:
#                         skipped_rows += 1
#                         continue
                    
#                     lat = float(row['lat'])
#                     long = float(row['long'])
                    
#                     # Parse các trường điểm số (cho phép giá trị rỗng)
#                     # Đọc từ CSV với tên cột gốc: avg_score, final_score
#                     avg_star = float(row['avg_score']) if row.get('avg_score') and row['avg_score'].strip() else None
#                     total_reviews = float(row['total_reviews']) if row.get('total_reviews') and row['total_reviews'].strip() else None
#                     normalize_stars_reviews = float(row['final_score']) if row.get('final_score') and row['final_score'].strip() else None
                    
#                     # Thêm vào batch
#                     batch_data.append((
#                         row['id'],
#                         row.get('name', ''),
#                         row.get('address', ''),
#                         lat,
#                         long,
#                         long,  # longitude
#                         lat,   # latitude
#                         row.get('poi_type', ''),
#                         avg_star,
#                         total_reviews,
#                         normalize_stars_reviews
#                     ))
                    
#                     # Insert batch khi đủ kích thước
#                     if len(batch_data) >= batch_size:
#                         execute_batch(cursor, """
#                             INSERT INTO poi_locations_uuid (id, name, address, lat, long, geom, poi_type, avg_star, total_reviews, normalize_stars_reviews)
#                             VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s)
#                             ON CONFLICT (id) DO UPDATE SET
#                                 name = EXCLUDED.name,
#                                 address = EXCLUDED.address,
#                                 lat = EXCLUDED.lat,
#                                 long = EXCLUDED.long,
#                                 geom = EXCLUDED.geom,
#                                 poi_type = EXCLUDED.poi_type,
#                                 avg_star = EXCLUDED.avg_star,
#                                 total_reviews = EXCLUDED.total_reviews,
#                                 normalize_stars_reviews = EXCLUDED.normalize_stars_reviews;
#                         """, batch_data)
                        
#                         conn.commit()
#                         total_rows += len(batch_data)
#                         print(f"  Đã import {total_rows} records...")
#                         batch_data = []
                        
#                 except (ValueError, KeyError) as e:
#                     print(f"⚠ Lỗi ở dòng: {row} - {e}")
#                     skipped_rows += 1
#                     continue
            
#             # Insert batch còn lại
#             if batch_data:
#                 execute_batch(cursor, """
#                     INSERT INTO poi_locations (id, name, address, lat, long, geom, poi_type, avg_star, total_reviews, normalize_stars_reviews)
#                     VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s)
#                     ON CONFLICT (id) DO UPDATE SET
#                         name = EXCLUDED.name,
#                         address = EXCLUDED.address,
#                         lat = EXCLUDED.lat,
#                         long = EXCLUDED.long,
#                         geom = EXCLUDED.geom,
#                         poi_type = EXCLUDED.poi_type,
#                         avg_star = EXCLUDED.avg_star,
#                         total_reviews = EXCLUDED.total_reviews,
#                         normalize_stars_reviews = EXCLUDED.normalize_stars_reviews;
#                 """, batch_data)
                
#                 conn.commit()
#                 total_rows += len(batch_data)
            
#             cursor.close()
            
#             print(f"\n✓ Hoàn thành!")
#             print(f"  - Tổng số records thành công: {total_rows}")
#             print(f"  - Số records bị bỏ qua: {skipped_rows}")
            
#     except Exception as e:
#         print(f"✗ Lỗi: {e}")
#         conn.rollback()
#         raise
    
#     finally:
#         conn.close()

# def verify_data(limit=5):
#     """Kiểm tra dữ liệu đã import"""
#     conn = psycopg2.connect(Config.get_db_connection_string())
#     cursor = conn.cursor()
    
#     # Đếm tổng số records
#     cursor.execute("SELECT COUNT(*) FROM poi_locations_uuid;")
#     count = cursor.fetchone()[0]
#     print(f"\n📊 Thống kê:")
#     print(f"  - Tổng số POI trong database: {count}")
    
#     # Hiển thị một vài records mẫu
#     cursor.execute(f"""
#         SELECT id, name, address, lat, long, poi_type, avg_star, total_reviews, normalize_stars_reviews, ST_AsText(geom) as geom_text
#         FROM poi_locations_uuid 
#         LIMIT {limit};
#     """)
    
#     print(f"\n📝 {limit} records mẫu:")
#     for row in cursor.fetchall():
#         name_display = row[1][:50] if row[1] else 'N/A'
#         print(f"  - {name_display}: ({row[3]}, {row[4]}) - {row[5]}")
#         print(f"    Address: {row[2][:50] if row[2] else 'N/A'}")
#         print(f"    Scores: avg={row[6]}, reviews={row[7]}, final={row[8]}")
#         print(f"    Geometry: {row[9]}")
    
#     cursor.close()
#     conn.close()

# if __name__ == "__main__":
#     # File CSV cần import
#     csv_file = "viamo_full.csv"
    
#     print("🚀 Bắt đầu import dữ liệu vào PostgreSQL...")
#     print(f"📁 File: {csv_file}")
#     print(f"🔗 Database: {Config.DB_NAME} @ {Config.DB_HOST}\n")
    
#     # Import dữ liệu
#     import_csv_to_postgres(csv_file, batch_size=100)
    
#     # Kiểm tra kết quả
#     verify_data(limit=5)








import csv
import psycopg2
from psycopg2.extras import execute_batch
from config.config import Config


def create_table_if_not_exists(conn):
    """Tạo table poi_locations_uuid nếu chưa tồn tại"""
    cursor = conn.cursor()

    # Enable PostGIS
    cursor.execute("""
        CREATE EXTENSION IF NOT EXISTS postgis;
    """)

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS poi_locations_uuid (
            id UUID PRIMARY KEY,
            name TEXT,
            address TEXT,
            lat DOUBLE PRECISION NOT NULL,
            long DOUBLE PRECISION NOT NULL,
            geom GEOMETRY(Point, 4326),
            poi_type TEXT,
            avg_star DOUBLE PRECISION,
            total_reviews DOUBLE PRECISION,
            normalize_stars_reviews DOUBLE PRECISION
        );
    """)

    # Create spatial index
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS poi_locations_uuid_geom_idx
        ON poi_locations_uuid USING GIST (geom);
    """)

    conn.commit()
    cursor.close()
    print("✓ Table poi_locations_uuid sẵn sàng")


def import_csv_to_postgres(csv_file_path, batch_size=100):
    """Import CSV vào PostgreSQL (upsert theo UUID)"""
    conn = psycopg2.connect(Config.get_db_connection_string())

    try:
        create_table_if_not_exists(conn)
        cursor = conn.cursor()

        with open(csv_file_path, "r", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            batch_data = []
            total_rows = 0
            skipped_rows = 0

            for row in reader:
                try:
                    if not row.get("id") or not row.get("lat") or not row.get("long"):
                        skipped_rows += 1
                        continue

                    lat = float(row["lat"])
                    long = float(row["long"])

                    avg_star = float(row["avg_score"]) if row.get("avg_score") else None
                    total_reviews = float(row["total_reviews"]) if row.get("total_reviews") else None
                    normalize_score = float(row["final_score"]) if row.get("final_score") else None

                    batch_data.append((
                        row["id"],
                        row.get("name"),
                        row.get("address"),
                        lat,
                        long,
                        long,  # longitude
                        lat,   # latitude
                        row.get("poi_type"),
                        avg_star,
                        total_reviews,
                        normalize_score
                    ))

                    if len(batch_data) >= batch_size:
                        execute_batch(cursor, UPSERT_SQL, batch_data)
                        conn.commit()
                        total_rows += len(batch_data)
                        batch_data.clear()
                        print(f"  Đã import {total_rows} records...")

                except Exception as e:
                    print(f"⚠ Bỏ qua dòng lỗi: {e}")
                    skipped_rows += 1

            if batch_data:
                execute_batch(cursor, UPSERT_SQL, batch_data)
                conn.commit()
                total_rows += len(batch_data)

        cursor.close()
        print("\n✓ IMPORT HOÀN TẤT")
        print(f"  - Thành công: {total_rows}")
        print(f"  - Bỏ qua: {skipped_rows}")

    except Exception as e:
        conn.rollback()
        print(f"✗ Lỗi: {e}")
        raise
    finally:
        conn.close()


UPSERT_SQL = """
INSERT INTO poi_locations_uuid
(id, name, address, lat, long, geom, poi_type, avg_star, total_reviews, normalize_stars_reviews)
VALUES (
    %s, %s, %s, %s, %s,
    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
    %s, %s, %s, %s
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    address = EXCLUDED.address,
    lat = EXCLUDED.lat,
    long = EXCLUDED.long,
    geom = EXCLUDED.geom,
    poi_type = EXCLUDED.poi_type,
    avg_star = EXCLUDED.avg_star,
    total_reviews = EXCLUDED.total_reviews,
    normalize_stars_reviews = EXCLUDED.normalize_stars_reviews;
"""


def verify_data(limit=5):
    """Kiểm tra dữ liệu"""
    conn = psycopg2.connect(Config.get_db_connection_string())
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM poi_locations_uuid;")
    print(f"\n📊 Tổng POI: {cursor.fetchone()[0]}")

    cursor.execute(f"""
        SELECT id, name, lat, long, poi_type, avg_star, total_reviews,
               normalize_stars_reviews, ST_AsText(geom)
        FROM poi_locations_uuid
        LIMIT {limit};
    """)

    print(f"\n📝 {limit} records mẫu:")
    for r in cursor.fetchall():
        print(f"- {r[1]} | ({r[2]}, {r[3]}) | {r[4]} | geom={r[8]}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    csv_file = "viamo_full.csv"

    print("🚀 BẮT ĐẦU IMPORT POI")
    print(f"📁 File: {csv_file}")
    print(f"🗄️ DB: {Config.DB_NAME}@{Config.DB_HOST}\n")

    import_csv_to_postgres(csv_file, batch_size=100)
    verify_data(limit=5)
