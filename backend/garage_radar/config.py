"""
Garage Radar — Application Config
Reads from environment variables (or .env file via pydantic-settings).
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/garage_radar"

    # Raw snapshot store
    snapshot_store_path: Path = Path("./data/snapshots")
    snapshot_store_backend: str = "local"  # or "s3"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # eBay API
    ebay_app_id: str = ""

    # Alerting
    sendgrid_api_key: str = ""
    alert_email_to: str = ""
    alert_email_from: str = "alerts@garage-radar.local"
    slack_webhook_url: str = ""

    # App behavior
    log_level: str = "INFO"

    # Crawler rate limits (requests per second)
    bat_rate_limit: float = 0.33       # 1 req / 3s
    carsandbids_rate_limit: float = 0.25  # 1 req / 4s
    pcarmarket_rate_limit: float = 0.17   # 1 req / 6s

    # Insight engine thresholds
    underpriced_alert_threshold: float = -0.15   # -15% vs cluster median
    underpriced_min_dollar: float = 2_000        # Must be ≥ $2k below median to alert
    price_drop_alert_threshold: float = 0.05     # 5% single-period OR cumulative drop
    price_drop_min_dollar: float = 1_500         # Must be ≥ $1.5k absolute drop to alert
    comp_cluster_min_size: int = 5
    comp_window_days: int = 90
    comp_window_thin_days: int = 180              # Extended for thin clusters


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
