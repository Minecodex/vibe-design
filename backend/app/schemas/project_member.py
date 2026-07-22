from datetime import datetime
from pydantic import BaseModel
from app.schemas.user import UserRead

class ProjectMemberCreate(BaseModel):
    user_id: int
    role: str = "editor"

class ProjectMemberRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    role: str
    created_at: datetime
    updated_at: datetime
    
    # Nested user for display
    user: UserRead | None = None

    model_config = {"from_attributes": True}
