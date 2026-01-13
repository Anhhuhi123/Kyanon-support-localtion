from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class PoiRequest(BaseModel):
    add: List[UUID] = Field(default_factory=list)
    update: List[UUID] = Field(default_factory=list)
    delete: List[UUID] = Field(default_factory=list)

class UuidRequest(BaseModel):
    id: list[UUID] = Field(
        default_factory=list,
        example=["0f9d2009-9436-46a4-b354-b0261898a39e"]
    )

