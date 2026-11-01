from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ShopOwned, TimestampMixin, string_enum
from app.models.enums import UserRole
from app.models.shops import Shop


class User(ShopOwned, TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)    # unique across ALL shops: it decides the shop at login
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))   # never the plain password
    role: Mapped[UserRole] = mapped_column(string_enum(UserRole, "user_role"), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(default=True)

    shop: Mapped[Shop] = relationship()
