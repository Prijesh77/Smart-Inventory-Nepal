"""User accounts: login check, creation and admin changes."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import UserCreate, UserUpdate


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email and password match an ACTIVE account, else None.

    The password is always hashed (against a dummy hash if the email is
    unknown), so response time does not reveal which emails exist.
    """
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    valid = verify_password(password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not valid or not user.is_active:
        return None
    return user


def create_user(db: Session, data: UserCreate) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise ConflictError(f"A user with email '{data.email}' already exists")
    user = User(email=data.email, full_name=data.full_name.strip(), role=data.role,
                hashed_password=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.email)))


def update_user(db: Session, user_id: int, data: UserUpdate, acting_user: User) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    changes = data.model_dump(exclude_unset=True)

    # Never leave the system without an active admin (e.g. an admin demoting themselves).
    losing_admin = user.role == UserRole.ADMIN and (
        changes.get("role", UserRole.ADMIN) != UserRole.ADMIN or changes.get("is_active", True) is False)
    if losing_admin:
        active_admins = db.scalar(select(func.count()).select_from(User).where(
            User.role == UserRole.ADMIN, User.is_active.is_(True)))
        if active_admins <= 1:
            raise AppError("This is the last active admin; create another admin first")
    if user.id == acting_user.id and changes.get("is_active") is False:
        raise AppError("You cannot deactivate your own account")

    if "password" in changes:
        user.hashed_password = hash_password(changes.pop("password"))
    for field, value in changes.items():
        setattr(user, field, value.strip() if field == "full_name" else value)
    db.commit()
    db.refresh(user)
    return user
