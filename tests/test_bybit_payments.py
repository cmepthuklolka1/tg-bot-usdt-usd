"""
Debug script to find Bybit P2P payment method IDs.
"""
import asyncio
from curl_cffi.requests import AsyncSession

URL = "https://api2.bybit.com/fiat/otc/item/online"

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.bybit.com",
    "Referer": "https://www.bybit.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

async def main():
    session = AsyncSession(impersonate="chrome110")

    # First: fetch without payment filter to get one item and inspect its structure
    payload = {
        "userId": "",
        "tokenId": "USDT",
        "currencyId": "RUB",
        "payment": [],  # No filter to get all
        "side": "1",
        "size": "3",
        "page": "1",
        "amount": "",
        "authMaker": False,
        "canTrade": False
    }

    res = await session.post(URL, headers=HEADERS, json=payload)
    data = res.json()
    
    items = data.get("result", {}).get("items", [])
    print(f"Found {len(items)} items\n")
    
    for i, item in enumerate(items[:3]):
        print(f"--- Item {i+1} ---")
        print(f"Price: {item.get('price')}")
        print(f"Advertiser: {item.get('advertiser', {}).get('nickName')}")
        print(f"Min amount: {item.get('minAmount')}")
        print(f"Max amount: {item.get('maxAmount')}")
        print(f"Payments: {item.get('payments')}")
        print()

    await session.close()

if __name__ == "__main__":
    asyncio.run(main())
