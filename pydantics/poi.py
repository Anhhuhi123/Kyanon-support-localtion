from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class PoiRequest(BaseModel):
    add: List[UUID] = Field(default_factory=list)
    update: List[UUID] = Field(default_factory=list)
    delete: List[UUID] = Field(default_factory=list)
