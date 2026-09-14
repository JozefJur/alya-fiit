"""Shared schema building blocks."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

#: Exact money/rate serialization: Decimal → "12.34" string in JSON.
MoneyStr = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.2f}", return_type=str)]
RateStr = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.4f}", return_type=str)]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageOut(ApiModel):
    message: str
