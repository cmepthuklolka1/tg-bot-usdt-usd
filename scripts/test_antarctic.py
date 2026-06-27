"""
Standalone script to test Antarctic Wallet USDT/RUB rate fetching.
Run: python scripts/test_antarctic.py
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from curl_cffi.requests import AsyncSession

RATES_URL = "https://app.antarcticwallet.com/api/v2/coins/rates"
CASH_ONRAMP_URL = "https://app.antarcticwallet.com/api/v3/buy/crypto/cash/exchange_rate/aw"
ANTARCTIC_SBP_URL = "https://app.antarcticwallet.com/api/v3/buy/crypto/exchange_rate/aw"
TOKENS_FILE = Path(__file__).resolve().parent.parent / "config" / "antarctic_tokens.json"


def load_token() -> str:
    with open(TOKENS_FILE) as f:
        return json.load(f)["access_token"]


def _scale_value(obj: dict) -> float:
    """Convert {amount: 1169434, scale: 8} → 0.01169434"""
    return obj["amount"] / (10 ** obj["scale"])


def _normalize_rate(rate) -> float:
    value = float(str(rate).replace(",", "."))
    return 1.0 / value if value < 1 else value


async def main():
    token = load_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    async with AsyncSession(impersonate="chrome110") as session:
        # 1. General rates (/v2/coins/rates)
        r = await session.get(RATES_URL, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        if data.get("status") != "ok":
            print(f"API error: {data}")
            return

        items = data.get("data", {}).get("items", [])
        currency = data.get("data", {}).get("currency", "?")

        print("=" * 50)
        print(f"  Antarctic Wallet — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Currency: {currency}")
        print("=" * 50)

        for item in items:
            coin = item["coin"]
            buy = float(item["buyRate"])
            sell = float(item["sellRate"])
            spread = buy - sell
            ttl = item.get("ttl", "?")

            print(f"\n  {coin}/{currency} (general rates):")
            print(f"    Buy rate:   {buy:.2f} {currency}")
            print(f"    Sell rate:  {sell:.2f} {currency}")
            print(f"    Spread:     {spread:.2f} {currency} ({spread / sell * 100:.1f}%)")
            print(f"    TTL:        {ttl} min")

        # 2. Onramp rates used by the current web app
        for title, url in (
            ("Cash/account onramp rate", CASH_ONRAMP_URL),
            ("Antarctic SBP provider rate", ANTARCTIC_SBP_URL),
        ):
            print("\n" + "=" * 50)
            print(f"  {title}")
            print("=" * 50)

            r2 = await session.get(url, headers=headers, timeout=15)
            r2.raise_for_status()
            data2 = r2.json()

            if data2.get("status") != "ok":
                print(f"  API error: {data2}")
            else:
                rate_obj = data2["data"]["rate"]
                if isinstance(rate_obj, dict):
                    rub_per_usdt = 1.0 / _scale_value(rate_obj)
                else:
                    rub_per_usdt = _normalize_rate(rate_obj)
                ttl = data2["data"].get("ttl", "?")

                print(f"\n  Endpoint:       {url}")
                print(f"  Raw rate:       {rate_obj}")
                print(f"  RUB per 1 USDT: {rub_per_usdt:.2f} RUB  <-- web app onramp price")
                print(f"  TTL:            {ttl} sec")

        print("\n" + "=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
