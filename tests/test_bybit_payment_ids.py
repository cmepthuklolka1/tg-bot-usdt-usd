"""
Inspect all payment IDs returned by Bybit P2P for RUB,
and check which IDs correspond to which payment methods.
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

    # Fetch WITHOUT any payment filter to see ALL IDs
    payload = {
        "userId": "",
        "tokenId": "USDT",
        "currencyId": "RUB",
        "payment": [],
        "side": "1",
        "size": "100",
        "page": "1",
        "amount": "",
        "authMaker": False,
        "canTrade": False
    }
    res = await session.post(URL, headers=HEADERS, json=payload)
    items = res.json().get("result", {}).get("items", [])

    # Collect all unique payment IDs across all items
    payment_to_sellers = {}  # id -> list of nickNames
    for item in items:
        nick = item.get("nickName", "?")
        stock = float(item.get("quantity", 0)) * float(item.get("price", 0))
        for pid in item.get("payments", []):
            if pid not in payment_to_sellers:
                payment_to_sellers[pid] = []
            payment_to_sellers[pid].append(f"{nick}(~{stock:.0f}₽)")

    print("=== All payment IDs found in API response ===")
    for pid, sellers in sorted(payment_to_sellers.items(), key=lambda x: int(x[0])):
        print(f"\nID: {pid}  ({len(sellers)} sellers)")
        for s in sellers[:3]:  # Show first 3 per ID
            print(f"   {s}")

    # Now fetch WITH our current filter ["14", "40"] to compare
    print("\n\n=== Results with filter ['14', '40'] and stock >= 100k ===")
    payload["payment"] = ["14", "40"]
    res2 = await session.post(URL, headers=HEADERS, json=payload)
    items2 = res2.json().get("result", {}).get("items", [])
    filtered = [i for i in items2 if i.get("quantity", 0) * float(i.get("price", 0)) >= 100_000]

    for i, item in enumerate(filtered[:10]):
        stock = item.get("quantity", 0) * float(item.get("price", 0))
        pids = item.get("payments", [])
        print(f"#{i+1} {item.get('nickName'):<20} price={item.get('price')} stock=~{stock:.0f}₽  payments={pids}")

    await session.close()

if __name__ == "__main__":
    asyncio.run(main())
