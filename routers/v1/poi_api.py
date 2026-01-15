import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import psycopg2
from fastapi import APIRouter
from pydantics.user import UserIdRequest 
from services.poi_service import PoiService

router = APIRouter(prefix="/api/v1/poi", tags=["Poi"])

@router.post("/visited")
def get_poi_visited(user_id: UserIdRequest):
    poi_ids =  PoiService.get_visited_pois_by_user(user_id)
    return PoiService.get_poi_by_ids(poi_ids)

# @router.post("/sync_pois")
# def sync_pois(payload: PoiRequest) -> dict:
#     conn = psycopg2.connect(Config.get_db_connection_string())
#     cursor = conn.cursor()

#     try:
#         add_ids = [str(i) for i in (payload.add or [])]
#         update_ids = [str(i) for i in (payload.update or [])]
#         delete_ids = [str(i) for i in (payload.delete or [])]

#         inserted = 0
#         updated = 0
#         deleted = 0

#         # =========================================================
#         # ADD — insert mới, nếu trùng id thì bỏ qua
#         # =========================================================
#         if add_ids:
#             cursor.execute(
#                 """
#                 SELECT
#                     id,
#                     name,
#                     address,
#                     lat,
#                     long,
#                     geom,
#                     poi_type,
#                     avg_star,
#                     total_reviews,
#                     normalize_stars_reviews
#                 FROM poi_locations_uuid
#                 WHERE id IN %s
#                 """,
#                 (tuple(add_ids),)
#             )

#             rows = cursor.fetchall()

#             insert_values = [
#                 (
#                     r[0],  # id
#                     r[1],  # name
#                     r[2],  # address
#                     r[3],  # lat
#                     r[4],  # long
#                     r[5],  # geom
#                     r[6],  # poi_type
#                     r[7],  # avg_star
#                     r[8],  # total_reviews
#                     r[9],  # normalize_stars_reviews
#                 )
#                 for r in rows
#             ]

#             cursor.executemany(
#                 """
#                 INSERT INTO poi_locations_uuid_test (
#                     id,
#                     name,
#                     address,
#                     lat,
#                     long,
#                     geom,
#                     poi_type,
#                     avg_star,
#                     total_reviews,
#                     normalize_stars_reviews
#                 )
#                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#                 ON CONFLICT (id) DO NOTHING
#                 """,
#                 insert_values
#             )

#             inserted = cursor.rowcount if cursor.rowcount > 0 else 0

#         # =========================================================
#         # UPDATE — chỉ update record đã tồn tại
#         # =========================================================
#         if update_ids:
#             cursor.execute(
#                 """
#                 SELECT
#                     id,
#                     name,
#                     address,
#                     lat,
#                     long,
#                     geom,
#                     poi_type,
#                     avg_star,
#                     total_reviews,
#                     normalize_stars_reviews
#                 FROM poi_locations_uuid
#                 WHERE id IN %s
#                 """,
#                 (tuple(update_ids),)
#             )

#             rows = cursor.fetchall()

#             update_values = [
#                 (
#                     r[1],  # name
#                     r[2],  # address
#                     r[3],  # lat
#                     r[4],  # long
#                     r[5],  # geom
#                     r[6],  # poi_type
#                     r[7],  # avg_star
#                     r[8],  # total_reviews
#                     r[9],  # normalize_stars_reviews
#                     r[0],  # id (WHERE)
#                 )
#                 for r in rows
#             ]

#             cursor.executemany(
#                 """
#                 UPDATE poi_locations_uuid_test
#                 SET
#                     name = %s,
#                     address = %s,
#                     lat = %s,
#                     long = %s,
#                     geom = %s,
#                     poi_type = %s,
#                     avg_star = %s,
#                     total_reviews = %s,
#                     normalize_stars_reviews = %s
#                 WHERE id = %s
#                 """,
#                 update_values
#             )

#             updated = cursor.rowcount if cursor.rowcount > 0 else 0

#         # =========================================================
#         # DELETE — xóa thẳng
#         # =========================================================
#         if delete_ids:
#             cursor.execute(
#                 "DELETE FROM poi_locations_uuid_test WHERE id IN %s",
#                 (tuple(delete_ids),)
#             )
#             deleted = cursor.rowcount if cursor.rowcount else 0

#         conn.commit()

#         return {
#             "inserted": inserted,
#             "updated": updated,
#             "deleted": deleted,
#         }

#     except Exception:
#         conn.rollback()
#         raise

#     finally:
#         cursor.close()
#         conn.close()


# @router.post("/clean_data")
# def clean_data(req: UuidRequest) -> dict:
#     poi_id = req.id[0] 
#     # with conn.cursor() as cur:
#     conn = psycopg2.connect(Config.get_db_connection_string())
#     cursor = conn.cursor()
#     cursor.execute(
#         'SELECT id, content, raw_data FROM "Poi" WHERE id = %s',
#         (str(poi_id),)
#     )
#     row = cursor.fetchone()

#     if not row:
#         raise HTTPException(status_code=404, detail="POI not found")

#     # Nếu cursor trả tuple → convert sang dict
#     colnames = [desc[0] for desc in cursor.description]
#     row_dict = dict(zip(colnames, row))

#     return map_poi_record(row_dict)
