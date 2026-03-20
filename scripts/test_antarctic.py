"""
Standalone script to test Antarctic Wallet USDT/RUB rate fetching.
Run: python scripts/test_antarctic.py
"""

import asyncio
from datetime import datetime

from curl_cffi.requests import AsyncSession

API_URL = "https://app.antarcticwallet.com/api/v2/coins/rates"
TOKEN = (
    "eyJhbGciOiJSUzI1NiJ9."
    "eyJ1c2VyX2lkIjo1NDI4MzMsImp0aSI6ImVjMzU1MzU5MGFhNzA0MTQ5MDlmMTAxNDBmNzI5MGEwIiwiaWF0IjoxNzc0MDMzOTc2LCJleHAiOjE3NzQ0NjU5NzZ9."
    "WztpMYLrbaBG4DyXc0QOXS3pQf_Jc1QoFbvE3FhFjrfXxlMK6zMY16S_JMEysJTGytIOnt86yq8KDzyB5kg3AUTLq1A0W87oA1-eTeQcf1mGM-itY0BqL5KL7-dCZQ1OliPPkfQm_vpJe84sPc_67wT4rr9ylagMdnxK3QWA-s06Lg_u54PCFZYFiflfqw2w7A1xyuEPqZe4DqGYGLnvtixq9euSULM3_DkVq0uX3lKmShgr2BTfyJ0Ofl0hKRKr7oLfzvwNCx2DwBBojEnCOm4j8TudmlMdtjwCTq1KRgjOb-tX7QvdG-NH5jHEp90wNNZBPolH2T15uI5dTWUjeA"
)


async def main():
    async with AsyncSession(impersonate="chrome110") as session:
        r = await session.get(
            API_URL,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/json",
            },
            timeout=15,
        )
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

            print(f"\n  {coin}/{currency}:")
            print(f"    Buy rate:   {buy:.2f} {currency}")
            print(f"    Sell rate:  {sell:.2f} {currency}")
            print(f"    Spread:     {spread:.2f} {currency} ({spread / sell * 100:.1f}%)")
            print(f"    TTL:        {ttl} min")

        print("\n" + "=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
