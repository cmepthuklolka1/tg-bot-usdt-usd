"""Antarctic Wallet — fetch USDT/RUB sell rate."""

import logging

from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import config

logger = logging.getLogger(__name__)

API_URL = "https://app.antarcticwallet.com/api/v2/coins/rates"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=15))
async def fetch_antarctic_sell_rate() -> float | None:
    """Returns the USDT/RUB sell rate from Antarctic Wallet, or None on failure."""
    token = getattr(config, "antarctic_token", None)
    if not token:
        logger.warning("Antarctic: ANTARCTIC_TOKEN not configured")
        return None

    session = AsyncSession(impersonate="chrome110")
    try:
        r = await session.get(
            API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            logger.warning(f"Antarctic: unexpected status: {data.get('status')}")
            return None
        for item in data.get("data", {}).get("items", []):
            if item.get("coin") == "USDT":
                return float(item["sellRate"])
        logger.warning("Antarctic: USDT not found in response")
        return None
    finally:
        await session.close()
