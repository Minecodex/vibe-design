from datetime import datetime as dt

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LicenseRecord(Base):
    __tablename__ = "license_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    license_token: Mapped[str] = mapped_column(String(4096), nullable=False)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
