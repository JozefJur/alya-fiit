"""Application settings.

All values can be overridden via environment variables with the ``ALYA_`` prefix
(e.g. ``ALYA_DATABASE_URL``) or a local ``backend/.env`` file. Defaults are safe
for local development only.
"""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALYA_", env_file=str(BACKEND_DIR / ".env"), extra="ignore"
    )

    database_url: str = f"sqlite:///{DATA_DIR / 'dev.db'}"

    # Auth — local development defaults; production values come from the environment.
    jwt_secret: str = "dev-only-secret-not-for-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 12 * 60

    # Domain defaults
    vat_rate: Decimal = Decimal("0.23")  # Slovak standard VAT rate
    default_low_stock_threshold: int = 5
    max_quantity_per_line: int = 10
    return_window_days: int = 14
    delivery_estimate_days: int = 2  # business days after shipping
    order_number_prefix: str = "AF"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
