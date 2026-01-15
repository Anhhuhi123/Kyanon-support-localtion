import csv
import psycopg2
from psycopg2.extras import execute_batch
from config.config import Config


UPSERT_SQL = """
INSERT INTO public."PoiClean" (
    id,
    name,
    address,
    lat,
    lon,
    geom,
    poi_type,
    avg_stars,
    total_reviews,
    stay_time,
    normalize_stars_reviews,
    created_at,
    "updatedAt",
    "deletedAt"
)
VALUES (
    %s, %s, %s, %s, %s,
    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
    %s, %s, %s, %s, %s,
    NOW(),
    NOW(),
    NULL
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    address = EXCLUDED.address,
    lat = EXCLUDED.lat,
    lon = EXCLUDED.lon,
    geom = EXCLUDED.geom,
    poi_type = EXCLUDED.poi_type,
    avg_stars = EXCLUDED.avg_stars,
    total_reviews = EXCLUDED.total_reviews,
    stay_time = EXCLUDED.stay_time,
    normalize_stars_reviews = EXCLUDED.normalize_stars_reviews,
    "updatedAt" = NOW();
"""


def import_csv_to_poi_clean(csv_file_path: str, batch_size: int = 500):
    print(Config.get_db_connection_string())
    conn = psycopg2.connect(Config.get_db_connection_string())

    total_rows = 0
    skipped_rows = 0

    try:
        cursor = conn.cursor()

        with open(csv_file_path, "r", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            batch_data = []

            for row in reader:
                try:
                    # Required fields
                    if not row.get("id") or not row.get("lat") or not row.get("lon"):
                        skipped_rows += 1
                        continue

                    lat = float(row["lat"])
                    lon = float(row["lon"])

                    # Validate coordinates
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        skipped_rows += 1
                        continue

                    avg_stars = float(row["avg_stars"]) if row.get("avg_stars") else None
                    total_reviews = int(row["total_reviews"]) if row.get("total_reviews") else None
                    stay_time = float(row["stay_time"]) if row.get("stay_time") else None
                    normalize_score = (
                        float(row["normalize_stars_reviews"])
                        if row.get("normalize_stars_reviews")
                        else None
                    )

                    batch_data.append((
                        row["id"],
                        row.get("name"),
                        row.get("address"),
                        lat,
                        lon,
                        lon,   # x for ST_MakePoint
                        lat,   # y for ST_MakePoint
                        row.get("poi_type"),
                        avg_stars,
                        total_reviews,
                        stay_time,
                        normalize_score
                    ))

                    if len(batch_data) >= batch_size:
                        execute_batch(cursor, UPSERT_SQL, batch_data)
                        conn.commit()
                        total_rows += len(batch_data)
                        batch_data.clear()
                        print(f"  ✓ Imported {total_rows} records...")

                except Exception as e:
                    skipped_rows += 1
                    print(f"⚠ Skip row: {e}")

            if batch_data:
                execute_batch(cursor, UPSERT_SQL, batch_data)
                conn.commit()
                total_rows += len(batch_data)

        cursor.close()

        print("\n🎉 IMPORT HOÀN TẤT")
        print(f"  - Thành công: {total_rows}")
        print(f"  - Bỏ qua: {skipped_rows}")

    except Exception as e:
        conn.rollback()
        print(f"❌ IMPORT FAILED: {e}")
        raise
    finally:
        conn.close()


def verify_data(limit: int = 5):
    conn = psycopg2.connect(Config.get_db_connection_string())
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT
            id,
            name,
            lat,
            lon,
            poi_type,
            avg_stars,
            total_reviews,
            stay_time,
            normalize_stars_reviews,
            ST_AsText(geom)
        FROM public."PoiClean"
        LIMIT {limit};
    """)

    print(f"\n🧪 SAMPLE DATA ({limit} rows):")
    for r in cursor.fetchall():
        print(
            f"- {r[1]} | ({r[2]}, {r[3]}) | "
            f"⭐ {r[5]} | reviews={r[6]} | stay={r[7]} | geom={r[9]}"
        )

    cursor.close()
    conn.close()


if __name__ == "__main__":
    csv_file = "./scripts/data_csv/data_clean_normalize.csv"

    print("🚀 START IMPORT PoiClean")
    print(f"📁 CSV: {csv_file}")
    print(f"🗄️ DB: {Config.DB_NAME}@{Config.DB_HOST}\n")

    import_csv_to_poi_clean(csv_file, batch_size=500)
    verify_data(limit=5)
