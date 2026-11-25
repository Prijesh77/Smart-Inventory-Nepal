from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas.auth import Token, UserOut
from app.services import users as service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token,
             summary="Log in with email (as 'username') and password; returns a bearer token. "
                     "remember=true keeps the login for remember_me_days (default 30) instead of 60 minutes.")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession,
          remember: Annotated[bool, Form(description="Keep me logged in on this device")] = False) -> Token:
    user = service.authenticate(db, form.username, form.password)
    if user is None:
        # Same message for wrong email, wrong password or inactive account.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    minutes = get_settings().remember_me_days * 24 * 60 if remember else None
    token, lifetime = create_access_token(user.id, user.role.value, expires_minutes=minutes)
    return Token(access_token=token, expires_in=lifetime, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="The logged-in user")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
