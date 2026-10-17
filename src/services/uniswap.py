"""Uniswap — fetch OWB/USDC price from DexScreener API."""

import logging

from ..utils.http import shared_session, check_response, request_timeout

from ..utils.retry import DEFAULT_RETRY

logger = logging.getLogger(__name__)

OWB_ADDRESS = "0xEF5997c2cf2f6c138196f8A6203afc335206b3c1"
API_URL = f"https://api.dexscreener.com/latest/dex/tokens/{OWB_ADDRESS}"


@DEFAULT_RETRY
async def fetch_owb_usdc_price() -> float | None:
    """Returns OWB price in USDC from Uniswap V3 (Base), or None on failure."""
    async with shared_session() as session:
        r = await session.get(API_URL, timeout=request_timeout())
        check_response(r)
        data = r.json()
        for pair in data.get("pairs", []):
            if pair.get("dexId") == "uniswap" and pair.get("quoteToken", {}).get("symbol") == "USDC":
                return float(pair["priceNative"])
        logger.warning("Uniswap: OWB/USDC pair not found in DexScreener response")
        return None
