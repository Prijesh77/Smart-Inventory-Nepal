"""Application errors and the handlers that turn them into consistent JSON responses.

Every error response has the same shape:  {"detail": "<human-readable message>"}
(422 validation errors keep FastAPI's standard list of field problems.)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT


class InvalidReferenceError(AppError):
    """A referenced record (e.g. category code, supplier id) does not exist."""
    status_code = 422   # Unprocessable Content


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # A database constraint caught something the service layer did not; never leak SQL details.
        logger.warning("Integrity error: %s", exc.orig)
        return JSONResponse(status_code=status.HTTP_409_CONFLICT,
                            content={"detail": "The request conflicts with existing data or a data rule."})
