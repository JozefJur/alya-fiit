"""Low-stock detection."""

from __future__ import annotations

from app.domain.entities.interfaces import StockLevelLike


class LowStockPolicy:
    """A variant is low-stock when ``available <= threshold``.

    The threshold is per-variant when set, otherwise the configured default.
    """

    def __init__(self, default_threshold: int) -> None:
        if default_threshold < 0:
            raise ValueError("default_threshold must be >= 0")
        self.default_threshold = default_threshold

    def threshold_for(self, stock: StockLevelLike) -> int:
        threshold = stock.low_stock_threshold
        if threshold is None:
            return self.default_threshold
        return threshold

    def is_low(self, stock: StockLevelLike) -> bool:
        available = stock.on_hand - stock.reserved
        return available < self.threshold_for(stock)
