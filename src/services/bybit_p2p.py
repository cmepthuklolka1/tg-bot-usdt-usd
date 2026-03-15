import logging
from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from ..domain.models import BybitP2PResponse, P2PItem

logger = logging.getLogger(__name__)

URL = "https://api2.bybit.com/fiat/otc/item/online"

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.bybit.com",
    "Referer": "https://www.bybit.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Payment method IDs for RUB market on Bybit P2P:
# "14" = Cash Deposit to Bank
# "18" = Mobile Top-Up / Phone Top-Up
# "40" = Bank Transfer (SBP / Sberbank / T-Bank etc.)
WANTED_PAYMENT_IDS = {"14", "18", "40"}

# API filter: pass wanted IDs so server pre-filters results server-side.
# The server returns a seller if ANY of their methods matches.
# We then apply a client-side whitelist to keep only sellers who have
# at least one of our wanted methods.
PAYMENT_IDS = list(WANTED_PAYMENT_IDS)

from ..utils.storage import BannedSellersStorage
banned_storage = BannedSellersStorage()

# side=1 means "Buy USDT" (user sells RUB, buys USDT)
PAYLOAD = {
    "userId": "",
    "tokenId": "USDT",
    "currencyId": "RUB",
    "payment": PAYMENT_IDS,
    "side": "1",
    "size": "100",  # Fetch large batch to have enough after filtering
    "page": "1",
    "amount": "",
    "authMaker": False,
    "canTrade": False
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=15))
async def fetch_bybit_p2p_rates(min_amount: float = 100_000.0) -> list[P2PItem]:
    """Fetches and filters P2P USDT/RUB rates from Bybit's internal JSON API."""
    session = AsyncSession(impersonate="chrome110")
    try:
        response = await session.post(URL, headers=HEADERS, json=PAYLOAD, timeout=15)
        response.raise_for_status()

        try:
            data = response.json()
            validated_response = BybitP2PResponse(**data)
        except Exception as e:
            logger.error(f"Bybit JSON schema mismatch: {e}")
            raise ValueError(f"Failed to validate Bybit response: {e}")

        if validated_response.retCode != 0:
            logger.warning(f"Bybit non-zero retCode: {validated_response.retMsg}")
            return []

        items = validated_response.result.items

        # Filter 1: maxAmount >= min_amount (user-configurable threshold)
        # Filter 2: seller must accept at least one of our wanted payment methods
        # Filter 3: seller must not be in the banned sellers blacklist
        banned_lower = {name.lower() for name in banned_storage.get_banned()}
        filtered = [
            item for item in items
            if item.maxAmount >= min_amount
            and bool(set(item.payments) & WANTED_PAYMENT_IDS)
            and item.nickName.lower() not in banned_lower
        ]

        logger.info(
            f"Bybit P2P: {len(items)} total, {len(filtered)} after maxAmount >= "
            f"{min_amount:.0f} RUB + payment whitelist + ban filter"
        )
        return filtered

    except Exception as e:
        logger.error(f"Failed to fetch Bybit P2P rates: {e}")
        raise
    finally:
        await session.close()
