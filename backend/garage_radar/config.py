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
        extra="ignore",
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

    # Vehicle targeting
    vehicle_target_preset: str = ""
    vehicle_targets_json: str = ""
    vehicle_target_make: str = "Porsche"
    vehicle_target_model: str = "911"
    vehicle_target_keywords: str = ""
    vehicle_target_year_min: int | None = 1965
    vehicle_target_year_max: int | None = 1998

    # Reference profile enrichment
    reference_cache_path: Path = Path("./data/reference_cache")
    reference_cache_ttl_hours: int = 168
    reference_miss_cache_ttl_hours: int = 12
    reference_request_timeout_s: float = 20.0
    reference_profile_budget_s: float = 8.0
    reference_user_agent: str = "GarageRadar/0.1 (https://github.com/tuckerrothmann/garage-radar)"
    vehicle_profile_cache_ttl_s: float = 300.0

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
    price_drop_alert_threshold: float = 0.05     # 5% drop
    comp_cluster_min_size: int = 5
    comp_window_days: int = 90
    comp_window_thin_days: int = 180              # Extended for thin clusters


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
