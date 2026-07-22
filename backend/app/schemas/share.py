from pydantic import BaseModel
from typing import Optional
from app.schemas.project import ProjectRead

class ShareUpdate(BaseModel):
    share_permission: Optional[str] = None # 'view', 'edit', or None (close sharing)
    share_password: Optional[str] = None
    share_expiration: Optional[int] = None

class ShareInfo(BaseModel):
    project: ProjectRead
    permission: str
    require_password: bool = False
    is_member: bool = False

class ShareAccess(BaseModel):
    password: Optional[str] = None
