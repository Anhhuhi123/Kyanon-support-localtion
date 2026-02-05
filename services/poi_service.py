import asyncpg
import json
import os
import pandas as pd
from typing import List, Optional, Dict, Any
from fastapi import HTTPException
from uuid import UUID
from typing import List
from dotenv import load_dotenv
from tqdm.asyncio import tqdm_asyncio
from openai import AsyncOpenAI
from utils.data_processing import process_poi_for_description, process_ingest_to_poi_clean, get_default_opening_hours
from utils.new_data_processing import new_process_poi_for_description
from utils.llm import process_batch
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BATCH_SIZE = 10

class PoiService:
    def __init__(self, db_pool: asyncpg.Pool = None, redis_client=None):
        """
        Khởi tạo POI service với async resources
        
        Args:
            db_pool: Async PostgreSQL connection pool
            redis_client: Async Redis client (reserved for future use)
        """
        self.db_pool = db_pool
        self.redis_client = redis_client
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    async def get_visited_pois_by_user(self, user_id: UUID) -> List[UUID]:
        """
        Lấy danh sách POI đã visit của user (ASYNC)
        
        Args:
            user_id: UUID của user
            
        Returns:
            List UUID của các POI đã visit
        """
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        try:
            async with self.db_pool.acquire() as conn:
                # 1. Lấy itinerary id
                itinerary = await conn.fetchrow(
                    'SELECT id FROM "UserItinerary" WHERE "userId" = $1',
                    user_id
                )
                
                if not itinerary:
                    # raise HTTPException(status_code=404, detail="Itinerary not found")
                    return []

                itinerary_id = itinerary["id"]

                # 2. Lấy danh sách POI đã visit
                rows = await conn.fetch(
                    'SELECT poi_id FROM "UserItineraryPoi" WHERE "user_itinerary_id" = $1',
                    itinerary_id
                )
                
                poi_ids = [row["poi_id"] for row in rows]
                return poi_ids
                
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_poi_by_ids(self, poi_ids: List[UUID]) -> List[dict]:
        """
        Lấy thông tin POI theo danh sách IDs (ASYNC)
        
        Args:
            poi_ids: List UUID của các POI
            
        Returns:
            List dict chứa thông tin POI
        """
        if not poi_ids:
            return []
        
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    'SELECT * FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                
                # Convert asyncpg.Record to dict
                return [dict(row) for row in rows]

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


    async def add_new_poi(self, poi_ids: List[UUID]) -> Dict[str, Any]:
        """
        Lấy thông tin POI từ bảng Poi theo danh sách IDs, 
        sau đó clean, normalize và insert/update vào bảng PoiClean.
        
        Quy trình:
        1. Lấy data từ bảng Poi theo id
        2. Clean data (xử lý null values, opening_hours)
        3. Insert/Update vào bảng PoiClean
        
        Args:
            poi_ids: List UUID của các POI cần xử lý
            
        Returns:
            Dict chứa kết quả: success_count, failed_count, failed_ids
        """
        
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        if not poi_ids:
            return {
                "success_count": 0,
                "failed_count": 0,
                "failed_ids": [],
                "message": "No POI IDs provided"
            }
        
        success_count = 0
        failed_count = 0
        failed_ids = []
        
        try:
            async with self.db_pool.acquire() as conn:
                # Step 1: Lấy data từ bảng Poi
                rows = await conn.fetch(
                    'SELECT id, content, raw_data, metadata FROM "Poi" WHERE "id" = ANY($1::uuid[])',
                    poi_ids
                )
                
                if not rows:
                    return {
                        "success_count": 0,
                        "failed_count": len(poi_ids),
                        "failed_ids": [str(pid) for pid in poi_ids],
                        "message": "No POI found with provided IDs"
                    }
                
                # Step 2 & 3: Process each POI (Extract -> Clean -> Normalize)
                for row in rows:
                    try:
                        poi_data = dict(row)
                        
                        #  add vô thôi chớ chưa có clean gì hết
                        processed_data = process_ingest_to_poi_clean(
                            poi_row=poi_data,
                        ) 
                        # Validate required fields
                        if not processed_data.get("lat") or not processed_data.get("lon"):
                            failed_count += 1
                            failed_ids.append(str(poi_data.get("id")))
                            continue
                        
                        # Step 4: Insert/Update vào bảng PoiClean
                        await self._upsert_poi_clean(conn, processed_data)
                        success_count += 1
                        
                    except Exception as e:
                        failed_count += 1
                        failed_ids.append(str(row.get("id")))
                        print(f"Error processing POI {row.get('id')}: {e}")
                
                return {
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_ids": failed_ids,
                    "message": f"Processed {success_count} POIs successfully, {failed_count} failed"
                }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def _upsert_poi_clean(self, conn: asyncpg.Connection, data: Dict[str, Any]):
        """
        Insert or Update POI data vào bảng PoiClean
        """

        # Convert opening_hours to JSON string
        opening_hours_json = json.dumps(data.get("opening_hours", []))

        upsert_sql = """
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
            open_hours,
            created_at,
            "updatedAt",
            "deletedAt"
        )
        VALUES (
            $1, $2, $3, $4, $5,
            ST_SetSRID(ST_MakePoint($6, $7), 4326),
            $8, $9, $10, $11,
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
            open_hours = EXCLUDED.open_hours,
            "updatedAt" = NOW();
        """

        await conn.execute(
            upsert_sql,
            data.get("id"),            # $1: id
            data.get("name"),          # $2: name
            data.get("address"),       # $3: address
            data.get("lat"),           # $4: lat
            data.get("lon"),           # $5: lon
            data.get("lon"),           # $6: x for ST_MakePoint
            data.get("lat"),           # $7: y for ST_MakePoint
            data.get("poi_type"),      # $8: poi_type
            data.get("avg_stars"),     # $9: avg_stars
            data.get("total_reviews"), # $10: total_reviews
            opening_hours_json         # $11: open_hours
        )

    async def generate_description(self, poi_ids: List[UUID]):
        """
        Lấy thông tin POI từ bảng Poi theo danh sách IDs, 
        sau đó clean, normalize và insert/update vào bảng PoiClean.
        
        Quy trình:
        1. Lấy data từ bảng Poi theo id
        2. Dùng llm để generate description
        3. Insert/Update vào bảng PoiClean
        
        Args:
            poi_ids: List UUID của các POI cần xử lý
            
        Returns:
            Dict chứa kết quả: success_count, failed_count, failed_ids
        """
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")

        if not poi_ids:
            return {
                "success_count": 0,
                "failed_count": 0,
                "failed_ids": [],
                "message": "No POI IDs provided"
            }

        failed_ids = []
        failed_count = 0

        # ===============================
        # FETCH POI DATA
        # ===============================
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT id, content, raw_data, metadata FROM "Poi" WHERE "id" = ANY($1::uuid[])',
                poi_ids
            )

        if not rows:
            return {
                "success_count": 0,
                "failed_count": len(poi_ids),
                "failed_ids": [str(pid) for pid in poi_ids],
                "message": "No POI found"
            }

        pois = []
        for row in rows:
            try:
                poi_data = dict(row)
                processed = process_poi_for_description(poi_data)
                pois.append(processed)
            except Exception as e:
                failed_count += 1
                failed_ids.append(str(row["id"]))
                print(f"Process POI error {row['id']}: {e}")

        # Dùng LLM để generate description
        # ===============================
        # LOAD BASE PROMPT
        # ===============================
        prompt_path = os.path.join(os.getcwd(), "scripts/generate_description/final_prompt_stay_time_default.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            base_prompt = f.read()

        poi_map = {poi["id"]: poi for poi in pois}
        poi_id_list = list(poi_map.keys())

        # ===============================
        # BATCHING
        # ===============================
        batches = [
            poi_id_list[i:i + BATCH_SIZE]
            for i in range(0, len(poi_id_list), BATCH_SIZE)
        ]

        tasks = [
            process_batch(
                batch_ids=batch,
                index=i,
                poi_map=poi_map,
                base_prompt=base_prompt,
                client=self.openai_client
            )
            for i, batch in enumerate(batches)
        ]

        results = []
        batch_results = await tqdm_asyncio.gather(*tasks)

        for batch in batch_results:
            results.extend(batch)

        # ===============================
        # UPDATE PoiClean TABLE
        # ===============================
        update_result = await self._update_poi_clean_from_llm(results)

        return {
            "success_count": update_result["updated_count"],
            "failed_count": failed_count + update_result["error_count"],
            "failed_ids": failed_ids + update_result["error_ids"],
            "data": results
        }


    async def _update_poi_clean_from_llm(self, llm_results: List[dict]) -> dict:
        """
        Update PoiClean table từ kết quả LLM.
        """

        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        error_ids = []
        
        async with self.db_pool.acquire() as conn:
            for poi in llm_results:
                # Skip None results (từ batch bị lỗi)
                if poi is None:
                    skipped_count += 1
                    continue
                
                poi_id = poi.get('id')
                if not poi_id:
                    skipped_count += 1
                    continue
                
                poi_type_clean = poi.get('poi_type_new')
                main_subcategory = poi.get('main_subcategory')
                specialization = poi.get('specialization')
                suitability = poi.get('suitability')
                stay_time = poi.get('stay_time')   

                # Convert suitability dict to JSON string
                suitability_json = json.dumps(suitability) if suitability else None
                
                try:
                    await conn.execute(
                        '''UPDATE "PoiClean"
                        SET poi_type_clean = $1,
                            main_subcategory = $2,
                            specialization = $3,
                            travel_type = $4,
                            stay_time = $5,              
                            "updatedAt" = NOW()
                        WHERE id = $6''',
                        poi_type_clean,
                        main_subcategory,
                        specialization,
                        suitability_json,
                        stay_time,                       
                        poi_id
                    )

                    updated_count += 1
                    
                    # Print progress every 100 records
                    if (updated_count + skipped_count) % 100 == 0:
                        print(f"Processed: {updated_count + skipped_count} records "
                            f"(Updated: {updated_count}, Skipped: {skipped_count})")
                
                except Exception as e:
                    error_count += 1
                    error_ids.append(str(poi_id))
                    print(f"Error updating POI {poi_id}: {e}")
        
        print(f"\n✓ Update complete!")
        print(f"Total Updated: {updated_count}")
        print(f"Total Skipped: {skipped_count}")
        print(f"Total Errors: {error_count}")
        
        return {
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "error_ids": error_ids
        }

 
    
    async def delete_poi(self, poi_ids: List[UUID]) -> Dict[str, Any]:
        """
        Xóa hẳn POI khỏi bảng PoiClean theo danh sách IDs.
        """
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")

        if not poi_ids:
            return {
                "deleted_count": 0,
                "not_found_ids": [],
                "message": "No POI IDs provided",
            }

        try:
            async with self.db_pool.acquire() as conn:
                # Lấy các id tồn tại
                existing_rows = await conn.fetch(
                    'SELECT id FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                    poi_ids,
                )
                existing_ids = [row["id"] for row in existing_rows]
                not_found_ids = [str(pid) for pid in poi_ids if pid not in existing_ids]

                deleted_count = 0
                if existing_ids:
                    # Hard delete
                    result = await conn.execute(
                        'DELETE FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                        existing_ids,
                    )
                    # asyncpg trả về dạng "DELETE <n>"
                    deleted_count = int(result.split()[-1]) if result else len(existing_ids)

                return {
                    "deleted_count": deleted_count,
                    "not_found_ids": not_found_ids,
                    "message": f"Deleted {deleted_count} POIs, {len(not_found_ids)} not found",
                }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def normalize_data(self) -> Dict[str, Any]:
        """
        Normalize normalize_stars_reviews cho toàn bộ POI bằng SQL (1 UPDATE duy nhất)
        """

        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")

        sql = """
        WITH stats AS (
            SELECT
                MIN(avg_stars) AS min_avg_stars,
                MAX(avg_stars) AS max_avg_stars,
                MAX(total_reviews) AS max_total_reviews
            FROM "PoiClean"
            WHERE "deletedAt" IS NULL
        )
        UPDATE "PoiClean" p
        SET
            normalize_stars_reviews = ROUND(
                (
                    (
                        CASE
                            WHEN s.max_avg_stars != s.min_avg_stars
                            THEN
                                (COALESCE(p.avg_stars, s.min_avg_stars) - s.min_avg_stars)
                                / (s.max_avg_stars - s.min_avg_stars)
                            ELSE
                                0.5
                        END
                    ) * 0.6
                    +
                    (
                        CASE
                            WHEN s.max_total_reviews > 0
                            THEN
                                LN(COALESCE(p.total_reviews, 1) + 1)
                                / LN(s.max_total_reviews + 1)
                            ELSE
                                0
                        END
                    ) * 0.4
                )::numeric
            , 3),
            "updatedAt" = NOW()
        FROM stats s
        WHERE p."deletedAt" IS NULL;
        """

        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(sql)

            return {
                "status": "success",
                "message": "Normalize completed successfully",
                "db_result": result
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def clean_poi_clean_table(self, poi_ids: List[str] = None) -> Dict[str, Any]:
        """
        Clean dữ liệu trong bảng PoiClean.
        
        Quy trình:
        - Lấy avg_stars, total_reviews, open_hours từ PoiClean
        - Nếu avg_stars hoặc total_reviews bị null:
          + avg_stars = MIN(avg_stars) trong PoiClean
          + total_reviews = 1
        - Nếu open_hours bị null -> set default 24/7
        
        Args:
            poi_ids: List UUID của các POI cần clean (None = clean tất cả)
            
        Returns:
            Dict chứa kết quả: success_count, failed_count, failed_ids
        """

        
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")

        if not poi_ids:
            return {
                "success_count": 0,
                "failed_count": 0,
                "failed_ids": [],
                "message": "No poi_ids provided, skip cleaning"
            }
        
        success_count = 0
        failed_count = 0
        failed_ids = []
        
        try:
            async with self.db_pool.acquire() as conn:
                # Lấy giá trị MIN của avg_stars từ PoiClean (chỉ lấy các giá trị không null)
                min_row = await conn.fetchrow(
                    'SELECT MIN(avg_stars) AS min_avg_stars FROM "PoiClean" WHERE avg_stars IS NOT NULL AND "deletedAt" IS NULL'
                )
                min_avg_stars = min_row["min_avg_stars"] if min_row and min_row["min_avg_stars"] else 1.0
                # Lấy data từ bảng PoiClean
                rows = await conn.fetch(
                    'SELECT id, avg_stars, total_reviews, open_hours FROM "PoiClean" WHERE "id" = ANY($1::uuid[]) AND "deletedAt" IS NULL',
                    poi_ids
                )

                if not rows:
                    return {
                        "success_count": 0,
                        "failed_count": len(poi_ids),
                        "failed_ids": [str(pid) for pid in poi_ids],
                        "message": "No POI found in PoiClean with provided IDs"
                    }
                
                # Clean từng POI
                for row in rows:
                    try:
                        poi_id = row["id"]
                        avg_stars = row["avg_stars"]
                        total_reviews = row["total_reviews"]
                        open_hours = row["open_hours"]
                        
                        # Flag để check có cần update không
                        need_update = False
                        
                        # Clean avg_stars và total_reviews
                        # Nếu avg_stars hoặc total_reviews bị null -> set giá trị mặc định
                        if avg_stars is None or total_reviews is None:
                            avg_stars = min_avg_stars if avg_stars is None else avg_stars
                            total_reviews = 1 if total_reviews is None or total_reviews == 0 else total_reviews
                            need_update = True
                        
                        # Clean open_hours - nếu null hoặc empty -> set default 24/7
                        if not open_hours:
                            open_hours = json.dumps(get_default_opening_hours())
                            need_update = True
                        
                        # Chỉ update nếu có thay đổi
                        if need_update:
                            await conn.execute(
                                '''UPDATE "PoiClean"
                                   SET avg_stars = $1,
                                       total_reviews = $2,
                                       open_hours = $3,
                                       "updatedAt" = NOW()
                                   WHERE id = $4''',
                                avg_stars,
                                total_reviews,
                                open_hours if isinstance(open_hours, str) else json.dumps(open_hours),
                                poi_id
                            )
                        
                        success_count += 1
                        
                    except Exception as e:
                        failed_count += 1
                        failed_ids.append(str(row.get("id")))
                        print(f"Error cleaning POI {row.get('id')}: {e}")
                
                return {
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "failed_ids": failed_ids,
                    "min_avg_stars_used": min_avg_stars,
                    "message": f"Cleaned {success_count} POIs successfully, {failed_count} failed"
                }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    

# ====================================LẤY DATA TRỰC TIẾP TỪ POICLEAN ĐỂ LLM GENERATION====================================== #
    async def new_generate_description(self, poi_ids: List[UUID]):
        if not self.db_pool:
            raise HTTPException(status_code=500, detail="Database pool not initialized")

        if not poi_ids:
            return {
                "success_count": 0,
                "failed_count": 0,
                "failed_ids": [],
                "message": "No POI IDs provided"
            }

        failed_ids = []
        failed_count = 0

        # ===============================
        # FETCH POI DATA
        # ===============================
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT id, poi_type, metadata FROM "PoiClean" WHERE "id" = ANY($1::uuid[])',
                poi_ids
            )

        if not rows:
            return {
                "success_count": 0,
                "failed_count": len(poi_ids),
                "failed_ids": [str(pid) for pid in poi_ids],
                "message": "No POI found"
            }

        pois = []
        for row in rows:
            try:
                poi_data = dict(row)
                processed = new_process_poi_for_description(poi_data)
                pois.append(processed)
            except Exception as e:
                failed_count += 1
                failed_ids.append(str(row["id"]))
                print(f"Process POI error {row['id']}: {e}")
                
        # Dùng LLM để generate description
        # ===============================
        # LOAD BASE PROMPT
        # ===============================
        prompt_path = os.path.join(os.getcwd(), "scripts/generate_description/final_prompt_stay_time_default.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            base_prompt = f.read()
                
        poi_map = {poi["id"]: poi for poi in pois}
        poi_id_list = list(poi_map.keys())

        # ===============================
        # BATCHING
        # ===============================
        batches = [
            poi_id_list[i:i + BATCH_SIZE]
            for i in range(0, len(poi_id_list), BATCH_SIZE)
        ]

        tasks = [
            process_batch(
                batch_ids=batch,
                index=i,
                poi_map=poi_map,
                base_prompt=base_prompt,
                client=self.openai_client
            )
            for i, batch in enumerate(batches)
        ]

        results = []
        batch_results = await tqdm_asyncio.gather(*tasks)

        for batch in batch_results:
            results.extend(batch)

        # ===============================
        # UPDATE PoiClean TABLE
        # ===============================
        update_result = await self._update_poi_clean_from_llm(results)

        return {
            "success_count": update_result["updated_count"],
            "failed_count": failed_count + update_result["error_count"],
            "failed_ids": failed_ids + update_result["error_ids"],
            "data": results
        }


