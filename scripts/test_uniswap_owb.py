"""
Standalone script to test OWB/USDC price fetching from DexScreener.
Run: python scripts/test_uniswap_owb.py
"""

import asyncio
from datetime import datetime

from curl_cffi.requests import AsyncSession

# OWB token on Base chain
OWB_ADDRESS = "0xEF5997c2cf2f6c138196f8A6203afc335206b3c1"
API_URL = f"https://api.dexscreener.com/latest/dex/tokens/{OWB_ADDRESS}"


async def main():
    async with AsyncSession(impersonate="chrome110") as session:
        r = await session.get(API_URL, timeout=15)
        r.raise_for_status()
        data = r.json()

        pairs = data.get("pairs", [])
        if not pairs:
            print("No pairs found for OWB")
            return

        print("=" * 55)
        print(f"  OWB Token --{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 55)

        # Find Uniswap OWB/USDC pair
        uniswap_pair = None
        for p in pairs:
            if p.get("dexId") == "uniswap" and p.get("quoteToken", {}).get("symbol") == "USDC":
                uniswap_pair = p
                break

        if uniswap_pair:
            price = uniswap_pair.get("priceNative", "?")
            price_usd = uniswap_pair.get("priceUsd", "?")
            liq = uniswap_pair.get("liquidity", {}).get("usd", 0)
            vol_24h = uniswap_pair.get("volume", {}).get("h24", 0)
            pool = uniswap_pair.get("pairAddress", "?")

            print(f"\n  [OK] Uniswap V3 (Base) -- OWB/USDC")
            print(f"    Price:       {price} USDC")
            print(f"    Price USD:   ${price_usd}")
            print(f"    Liquidity:   ${liq:,.2f}")
            print(f"    Volume 24h:  ${vol_24h:,.2f}")
            print(f"    Pool:        {pool}")
        else:
            print("\n  [!] Uniswap OWB/USDC pair not found")

        # Show all available pairs for reference
        print(f"\n  All pairs ({len(pairs)}):")
        for p in pairs:
            dex = p.get("dexId", "?")
            base = p.get("baseToken", {}).get("symbol", "?")
            quote = p.get("quoteToken", {}).get("symbol", "?")
            price = p.get("priceNative", "?")
            liq = p.get("liquidity", {}).get("usd", 0)
            print(f"    {dex:<12} {base}/{quote:<6}  price={price}  liq=${liq:,.0f}")

        print("\n" + "=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
