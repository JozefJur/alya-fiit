"""Maps typed domain errors to the consistent HTTP error envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

_STATUS_BY_TYPE: list[tuple[type[DomainError], int]] = [
    (AuthenticationError, 401),
    (NotFoundError, 404),
    (PermissionDeniedError, 403),
    (ValidationError, 422),
    (ConflictError, 409),
]


def _status_for(error: DomainError) -> int:
    for error_type, status in _STATUS_BY_TYPE:
        if isinstance(error, error_type):
            return status
    return 400


def envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=_status_for(error),
            content=envelope(error.code, error.message, error.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_schema_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=envelope(
                "validation_error",
                _describe_schema_errors(error),
                {"errors": jsonable_encoder(error.errors())},
            ),
        )


def _describe_schema_errors(error: RequestValidationError) -> str:
    """Turn Pydantic's error list into one sentence a user can act on."""
    problems = []
    for item in error.errors():
        location = [str(part) for part in item.get("loc", ()) if part not in ("body", "query")]
        field = ".".join(location) or "request"
        problems.append(f"{field}: {item.get('msg', 'invalid value')}")
    if not problems:
        return "The request is not valid."
    return "The request is not valid — " + "; ".join(problems[:5]) + "."
