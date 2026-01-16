from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class PoiRequest(BaseModel):
    add: List[UUID] = Field(default_factory=list)
    update: List[UUID] = Field(default_factory=list)
    delete: List[UUID] = Field(default_factory=list)

class SelectedPoiRequest(BaseModel):
    user_id: Optional[UUID] = Field(
        None,
        example="816d05bf-5b65-49d2-9087-77c4c83be655"
    )
    poi_id: Optional[UUID] = Field(
        None,
        example="816d05bf-5b65-49d2-9087-77c4c83be655"
    )
    route_id: int = Field(
        0,
        example=1
    )