from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.base_model import TimestampMixin, SoftDeleteMixin


class UserProvider(TimestampMixin, SoftDeleteMixin, Base):
    """Tracks which providers a user has installed."""

    __tablename__ = "user_providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)


class ProviderCredential(TimestampMixin, SoftDeleteMixin, Base):
    """Stores AK/SK credentials for a provider."""

    __tablename__ = "provider_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    access_key: Mapped[str] = mapped_column(String(500), nullable=False)
    secret_key: Mapped[str] = mapped_column(String(500), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(20), nullable=False, default="ak_sk")


class ProviderModel(TimestampMixin, SoftDeleteMixin, Base):
    """Stores model configurations for a provider."""

    __tablename__ = "provider_models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    credential_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("provider_credentials.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
