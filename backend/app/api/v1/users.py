"""User management. Admin only."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_roles
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.services import users as service

router = APIRouter(prefix="/users", tags=["users (admin)"])
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession, _: AdminUser) -> list[User]:
    return service.list_users(db)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             summary="Create an account (409 if the email exists)")
def create_user(data: UserCreate, db: DbSession, _: AdminUser) -> User:
    return service.create_user(db, data)


@router.patch("/{user_id}", response_model=UserOut,
              summary="Change name, role, active status or password")
def update_user(user_id: int, data: UserUpdate, db: DbSession, admin: AdminUser) -> User:
    return service.update_user(db, user_id, data, acting_user=admin)
