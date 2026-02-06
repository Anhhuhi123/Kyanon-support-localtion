import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from fastapi import APIRouter, HTTPException
from pydantics.user import UserIdRequest 
from pydantics.poi import ConfirmReplaceRequest, PoiRequest
from services.poi_service import PoiService
from services.ingest_poi_to_qdrant import IngestPoiToQdrantService
from services.route_service import RouteService
router = APIRouter(prefix="/api/v1/poi", tags=["Poi"])

# Service instance sẽ được set từ server.py startup event
poi_service: PoiService = None
search_service : RouteService = None  # Will be set from server.py
ingest_qdrant_service: IngestPoiToQdrantService = None  # Will be set from server.py

def get_search_service():
    """Lấy singleton instance của search service"""
    global search_service
    if search_service is None:
        raise HTTPException(
            status_code=500, 
            detail="Search service not initialized. Server may not have completed startup."
        )
    return search_service

@router.post("/visited")
async def get_poi_visited(user_id: UserIdRequest):
    """
    Lấy danh sách POI đã visit của user (ASYNC)
    
    Args:
        user_id: UUID của user
        
    Returns:
        List POI đã visit
    """
    if poi_service is None:
        raise HTTPException(status_code=500, detail="POI service not initialized")
    
    try:
        poi_ids = await poi_service.get_visited_pois_by_user(user_id.user_id)
        return await poi_service.get_poi_by_ids(poi_ids)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/confirm-replace")
async def confirm_replace_poi(req: ConfirmReplaceRequest):
    """
    Xác nhận thay thế POI và cập nhật cache
    
    Args:
        req: ConfirmReplaceRequest chứa user_id, route_id, old_poi_id, new_poi_id
        
    Returns:
        Dict chứa thông tin route đã được cập nhật
    """
    service = get_search_service()
    
    try:
        result = await service.confirm_replace_poi(
            user_id=req.user_id,
            route_id=req.route_id,
            old_poi_id=req.old_poi_id,
            new_poi_id=req.new_poi_id
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# @router.post("/update-poi-clean")
# async def sync_pois(payload: PoiRequest) -> dict:

#     if poi_service is None:
#         raise HTTPException(status_code=500, detail="POI service not initialized")
    
#     if ingest_qdrant_service is None:
#         raise HTTPException(status_code=500, detail="Ingest Qdrant service not initialized")

#     add_ids = [str(i) for i in (payload.add or [])]
#     delete_ids = [str(i) for i in (payload.delete or [])]
#     try: 
#         # xử lí trùng lặp id giữa add và update và delete
#         add_set = set(add_ids)
#         delete_set = set(delete_ids)
#         final_add_ids = list(add_set - delete_set)
#         final_delete_ids = list(delete_set)
        
#         if final_add_ids:
#             result_add = await poi_service.add_new_poi(final_add_ids)
#         if final_delete_ids:
#             result_delete = await poi_service.delete_poi(final_delete_ids) 
#         # clean trong bảng poi_clean
#         result_clean = await poi_service.clean_poi_clean_table(final_add_ids)
#         # service llm generate description
#         result_llm_gen = await poi_service.generate_description(final_add_ids)
#         # normalize lại total_reviews sau khi thêm mới và cập nhật (normalize toàn bộ PoiClean)
#         result_normalize = await poi_service.normalize_data()
#         # Ingest toàn bộ PoiClean vào Qdrant
#         result_qdrant = await ingest_qdrant_service.ingest_all_poi()
        
#         return {
#             "inserted": result_add if final_add_ids else None,
#             "deleted": result_delete if final_delete_ids else None,
#             "result_clean": result_clean,
#             "result_llm_gen": result_llm_gen,
#             "result_normalize": result_normalize,
#             "result_qdrant": result_qdrant
#         }
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/new-update-poi-clean")
async def new_sync_pois(payload: PoiRequest) -> dict:

    if poi_service is None:
        raise HTTPException(status_code=500, detail="POI service not initialized")
    
    if ingest_qdrant_service is None:
        raise HTTPException(status_code=500, detail="Ingest Qdrant service not initialized")

    add_ids = [str(i) for i in (payload.sync_id or [])]
    delete_ids = [str(i) for i in (payload.delete_id or [])]
    try: 
        # xử lí trùng lặp id giữa add và update và delete
        add_set = set(add_ids)
        delete_set = set(delete_ids)
        final_add_ids = list(add_set - delete_set)
        final_delete_ids = list(delete_set)
        
        if final_delete_ids:
            result_delete = await poi_service.delete_poi(final_delete_ids)
        
        # clean trong bảng poi_clean
        result_clean = await poi_service.clean_poi_clean_table(final_add_ids)
        # service llm generate description
        result_llm_gen = await poi_service.new_generate_description(final_add_ids)
        # normalize lại total_reviews sau khi thêm mới và cập nhật (normalize toàn bộ PoiClean)
        result_normalize = await poi_service.normalize_data()
        # Ingest toàn bộ PoiClean vào Qdrant
        result_qdrant = await ingest_qdrant_service.ingest_all_poi()
          
        return {
            "deleted": result_delete if final_delete_ids else None,
            "result_clean": result_clean,
            "result_llm_gen": result_llm_gen,
            "result_normalize": result_normalize,
            "result_qdrant": result_qdrant
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")