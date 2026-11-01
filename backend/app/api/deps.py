"""Shared request dependencies: who is calling, and are they allowed?

Usage in a router:
    def endpoint(user: CurrentUser): ...                      # any logged-in user
    @router.post(..., dependencies=[RequireManager])          # manager or admin only
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.models.enums import UserRole

# tokenUrl powers the "Authorize" button on /docs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def get_current_user(db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """401 if the token is missing, forged, expired, or the account no longer exists or is inactive."""
    try:
        user_id = int(decode_access_token(token)["sub"])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired, please log in again") from None
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise _unauthorized("Invalid authentication token") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Account not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    """Dependency that allows only the given roles (403 for everyone else)."""
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"This action needs one of these roles: {', '.join(r.value for r in roles)}")
        return user
    return check


RequireManager = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))
RequireAdmin = Depends(require_roles(UserRole.ADMIN))
