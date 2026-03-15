import json
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

    # Wait configurations for fetching
    fetch_timeout: int = Field(default=15)
    fetch_retries: int = Field(default=3)

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / '.env'),
        env_file_encoding='utf-8',
        extra='ignore'
    )

try:
    config = Settings()
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    # Initialize with dummy values for testing if .env is missing 
    # (In a real app, you might want this to crash gracefully)
    config = Settings(bot_token="dummy", admin_id=0)

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
