"""ABCEX exchange — fetch USDT/RUB last price."""

import logging

from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://hub.abcex.io/api"
INSTRUMENT = "USDTRUB"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=15))
async def fetch_abcex_last_price() -> float | None:
    """Returns the last USDT/RUB price from ABCEX, or None on failure."""
    session = AsyncSession(impersonate="chrome110")
    try:
        r = await session.get(
            f"{BASE_URL}/v2/exchange/public/candle/spot/ticker/day",
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        for ticker in data.get("tickers", []):
            if ticker.get("symbol") == INSTRUMENT:
                return float(ticker["lastPrice"])
        logger.warning("ABCEX: USDTRUB ticker not found in response")
        return None
    finally:
        await session.close()
