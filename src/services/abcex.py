"""ABCEX exchange — fetch USDT/RUB buy/sell prices from orderbook."""

import logging

from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://hub.abcex.io/api"
INSTRUMENT = "USDTRUB"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=15))
async def fetch_abcex_prices() -> tuple[float, float] | None:
    """Returns (buy, sell) prices from ABCEX orderbook, or None on failure."""
    session = AsyncSession(impersonate="chrome110")
    try:
        r = await session.get(
            f"{BASE_URL}/v2/exchange/public/orderbook/depth",
            params={"instrumentCode": INSTRUMENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        bids = data.get("bid", [])
        asks = data.get("ask", [])
        if not bids or not asks:
            logger.warning("ABCEX: empty orderbook for %s", INSTRUMENT)
            return None
        # ask = цена покупки (buy), bid = цена продажи (sell)
        return (float(asks[0]["price"]), float(bids[0]["price"]))
    finally:
        await session.close()
