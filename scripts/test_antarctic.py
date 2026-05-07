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
ONRAMP_URL = "https://app.antarcticwallet.com/api/v3/topup/rub/exchange_rate"
TOKENS_FILE = Path(__file__).resolve().parent.parent / "config" / "antarctic_tokens.json"


def load_token() -> str:
    with open(TOKENS_FILE) as f:
        return json.load(f)["access_token"]


def _scale_value(obj: dict) -> float:
    """Convert {amount: 1169434, scale: 8} → 0.01169434"""
    return obj["amount"] / (10 ** obj["scale"])


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

        # 2. Onramp SBP rate (/v3/topup/rub/exchange_rate)
        print("\n" + "=" * 50)
        print("  Onramp SBP rate (topup/rub/exchange_rate)")
        print("=" * 50)

        r2 = await session.get(ONRAMP_URL, headers=headers, timeout=15)
        r2.raise_for_status()
        data2 = r2.json()

        if data2.get("status") != "ok":
            print(f"  API error: {data2}")
        else:
            rate_obj = data2["data"]["rate"]
            rate_usdt_per_rub = _scale_value(rate_obj)
            rub_per_usdt = 1.0 / rate_usdt_per_rub
            ttl = data2["data"].get("ttl", "?")

            print(f"\n  Raw rate:       {rate_obj}")
            print(f"  USDT per 1 RUB: {rate_usdt_per_rub:.8f}")
            print(f"  RUB per 1 USDT: {rub_per_usdt:.2f} RUB  <-- onramp buy price")
            print(f"  TTL:            {ttl} sec")

        print("\n" + "=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
