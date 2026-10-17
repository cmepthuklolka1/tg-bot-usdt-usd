import json
import os
import logging
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)

# Base directory
BASE_DIR = Path(__file__).parent.parent

class Settings(BaseSettings):
    bot_token: str = Field(..., env='BOT_TOKEN')
    admin_id: int = Field(..., env='ADMIN_ID')

    # Path to whitelist file
    whitelist_path: Path = Field(default=BASE_DIR / 'config' / 'whitelist.json')
    banned_sellers_path: Path = Field(default=BASE_DIR / 'config' / 'banned_sellers.json')

    # User display settings
    user_settings_path: Path = Field(default=BASE_DIR / 'config' / 'user_settings.json')

    # Antarctic Wallet tokens file
    antarctic_tokens_path: Path = Field(default=BASE_DIR / 'config' / 'antarctic_tokens.json')

    # Wait configurations for fetching
    pinned_messages_path: Path = Field(default=BASE_DIR / 'config' / 'pinned_messages.json')
    runtime_state_path: Path = Field(default=BASE_DIR / 'config' / 'runtime_state.json')
    fetch_timeout: float = Field(default=15, gt=0, le=60)
    connect_timeout: float = Field(default=4, gt=0, le=15)
    fetch_retries: int = Field(default=3, ge=1, le=5)
    source_timeout: float = Field(default=40, gt=0, le=120)
    report_timeout: float = Field(default=45, gt=0, le=180)
    cache_ttl: float = Field(default=30, ge=0)
    max_stale_seconds: int = Field(default=3600, ge=0)
    recovery_interval: float = Field(default=60, ge=1)
    notification_failures: int = Field(default=2, ge=1)
    notification_reminder: int = Field(default=3600, ge=60)
    update_interval: float = Field(default=3600, ge=1)
    max_http_clients: int = Field(default=6, ge=1, le=20)

    model_config = SettingsConfigDict(
        env_file=os.environ.get('BOT_ENV_FILE', str(BASE_DIR / '.env')),
        env_file_encoding='utf-8',
        extra='ignore'
    )

try:
    config = Settings()
except Exception:
    logger.exception("Failed to load configuration. Check BOT_TOKEN and ADMIN_ID in .env")
    raise

def init_whitelist():
    """Ensure whitelist.json exists and has correct structure"""
    config.whitelist_path.parent.mkdir(parents=True, exist_ok=True)
    if not config.whitelist_path.exists():
        with open(config.whitelist_path, 'w', encoding='utf-8') as f:
            json.dump({'users': [config.admin_id]}, f, indent=4)
        logger.info(f"Created new whitelist file at {config.whitelist_path}")

def init_banned_sellers():
    """Ensure banned_sellers.json exists and has correct structure"""
    config.banned_sellers_path.parent.mkdir(parents=True, exist_ok=True)
    if not config.banned_sellers_path.exists():
        with open(config.banned_sellers_path, 'w', encoding='utf-8') as f:
            json.dump({'banned': []}, f, indent=4)
        logger.info(f"Created new banned sellers file at {config.banned_sellers_path}")

def init_user_settings():
    """Ensure user_settings.json exists and has correct structure"""
    config.user_settings_path.parent.mkdir(parents=True, exist_ok=True)
    if not config.user_settings_path.exists():
        with open(config.user_settings_path, 'w', encoding='utf-8') as f:
            json.dump({'users': {}}, f, indent=4)
        logger.info(f"Created new user settings file at {config.user_settings_path}")
