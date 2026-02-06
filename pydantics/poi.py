from pydantic import BaseModel, Field
from typing import List
from uuid import UUID
from typing import Optional

class PoiRequest(BaseModel):
    sync_ids: List[UUID] = Field(default_factory=list)
    delete_ids: List[UUID] = Field(default_factory=list)

class ConfirmReplaceRequest(BaseModel):
    user_id: UUID = Field(
        ...,
        example="816d05bf-5b65-49d2-9087-77c4c83be655"
    )
    route_id: str = Field(
        ...,
        example="1"
    )
    old_poi_id: str = Field(
        ...,
        example="7c1a4804-6fb2-4a01-95cb-3bc65bc13cdd"
    )
    new_poi_id: str = Field(
        ...,
        example="48f858ab-f9a9-423e-b1c4-255faac66aca"
    )