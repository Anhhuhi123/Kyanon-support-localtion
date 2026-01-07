import csv
import psycopg2
from psycopg2.extras import execute_batch
from config.config import Config


def create_table_if_not_exists(conn):
    """Tạo table poi_locations_uuid_test nếu chưa tồn tại"""
    cursor = conn.cursor()

    # Enable PostGIS
    cursor.execute("""
        CREATE EXTENSION IF NOT EXISTS postgis;
    """)

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS poi_locations_uuid_test (
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
        CREATE INDEX IF NOT EXISTS poi_locations_uuid_test_geom_idx
        ON poi_locations_uuid_test USING GIST (geom);
    """)

    conn.commit()
    cursor.close()
    print("✓ Table poi_locations_uuid_test sẵn sàng")


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
INSERT INTO poi_locations_uuid_test
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

    cursor.execute("SELECT COUNT(*) FROM poi_locations_uuid_test;")
    print(f"\n📊 Tổng POI: {cursor.fetchone()[0]}")

    cursor.execute(f"""
        SELECT id, name, lat, long, poi_type, avg_star, total_reviews,
               normalize_stars_reviews, ST_AsText(geom)
        FROM poi_locations_uuid_test
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
