from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH
from app.models.enums import UserRole

Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=128,
                                description=f"At least {MIN_PASSWORD_LENGTH} characters")]
# A simple shape check (something@something.something); the app sends no email, so no deeper check is needed.
Email = Annotated[str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")
    user: UserOut


class UserCreate(BaseModel):
    email: Email
    full_name: str = Field(min_length=1, max_length=120)
    password: Password
    role: UserRole = UserRole.VIEWER

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class UserUpdate(BaseModel):
    """Admin changes to an account. Only the fields sent are changed."""

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    password: Password | None = None
