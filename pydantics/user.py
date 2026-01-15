from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional


class UserIdRequest(BaseModel):
    user_id: Optional[UUID] = Field(
        default=None,
        example="816d05bf-5b65-49d2-9087-77c4c83be655"
    )
