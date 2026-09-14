"""Typed domain/application errors.

The API layer maps these to the consistent HTTP error envelope
(see docs/architecture.md, section 7). Domain code never imports FastAPI.
"""

from typing import Any


class DomainError(Exception):
    """Base class for all expected, typed failures."""

    code = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DomainError):
    """Semantically invalid input (beyond schema validation). HTTP 422."""

    code = "validation_error"


class NotFoundError(DomainError):
    """Missing resource, or a resource the caller must not know exists. HTTP 404."""

    code = "not_found"


class AuthenticationError(DomainError):
    """Missing/invalid credentials or token. HTTP 401."""

    code = "not_authenticated"


class PermissionDeniedError(DomainError):
    """Role or ownership rule violated. HTTP 403."""

    code = "not_authorized"


class ConflictError(DomainError):
    """Domain rule violation in the current state. HTTP 409."""

    code = "conflict"


class InvalidQuantityError(ValidationError):
    code = "invalid_quantity"


class ProductNotAvailableError(ConflictError):
    """Inactive product/variant/category — cannot be carted or ordered."""

    code = "product_not_available"


class InsufficientStockError(ConflictError):
    code = "insufficient_stock"


class CouponNotEligibleError(ConflictError):
    """Carries a machine-readable reason (expired, below_minimum, exhausted, ...)."""

    code = "coupon_not_eligible"

    def __init__(self, message: str, *, reason: str, details: dict[str, Any] | None = None) -> None:
        merged = {"reason": reason, **(details or {})}
        super().__init__(message, details=merged)
        self.reason = reason


class InvalidStateTransitionError(ConflictError):
    code = "invalid_state_transition"


class DuplicateCallbackError(ConflictError):
    """Same idempotency key replayed with a conflicting payload. HTTP 409."""

    code = "duplicate_callback_conflict"


class CsvImportError(ValidationError):
    """CSV import rejected; ``details['row_errors']`` lists per-row problems."""

    code = "csv_import_error"
