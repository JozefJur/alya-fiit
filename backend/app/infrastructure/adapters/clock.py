"""Time source abstraction — lets tests freeze or shift time deterministically."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time as a naive UTC datetime (project-wide convention)."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)


class FixedClock:
    """Test double: always returns the configured instant."""

    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant
