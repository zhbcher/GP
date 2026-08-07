from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "stock-watchlist"
    app_version: str = "1.0.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = ""
    timezone: str = "Asia/Shanghai"
    mootdx_tcp_port: int = 7709
    akshare_rate_limit: float = 1.0
    realtime_poll_interval: int = 3
    # Auth
    auth_enabled: bool = True
    auth_key: str = ""  # static access key; empty = open access
    # Industry news AI digest (P4)
    news_ai_provider: str = ""  # "api" or "" (disabled)
    news_ai_api_key: str = ""
    news_ai_base_url: str = "https://integrate.api.nvidia.com/v1"
    news_ai_model: str = "stepfun-ai/step-3.7-flash"
    # Feishu webhook for alert notifications
    feishu_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.database_url:
        # __file__ = backend/app/config.py → go up 2 levels → project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        db_dir = os.path.join(project_root, "data")
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "stock.db")
        object.__setattr__(s, 'database_url', f"sqlite+aiosqlite:///{db_path}")
    return s