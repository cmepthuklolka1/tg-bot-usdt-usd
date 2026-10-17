"""ABCEX exchange — fetch USDT/RUB buy/sell prices from orderbook."""

import logging

from ..utils.http import shared_session, check_response, request_timeout

from ..utils.retry import DEFAULT_RETRY

logger = logging.getLogger(__name__)

BASE_URL = "https://hub.abcex.io/api"
INSTRUMENT = "USDTRUB"


@DEFAULT_RETRY
async def fetch_abcex_prices() -> tuple[float, float] | None:
    """Returns (buy, sell) prices from ABCEX orderbook, or None on failure."""
    async with shared_session() as session:
        r = await session.get(
            f"{BASE_URL}/v2/exchange/public/orderbook/depth",
            params={"instrumentCode": INSTRUMENT},
            timeout=request_timeout(),
        )
        check_response(r)
        data = r.json()
        bids = data.get("bid", [])
        asks = data.get("ask", [])
        if not bids or not asks:
            logger.warning("ABCEX: empty orderbook for %s", INSTRUMENT)
            return None
        # ask = цена покупки (buy), bid = цена продажи (sell)
        return (float(asks[0]["price"]), float(bids[0]["price"]))
