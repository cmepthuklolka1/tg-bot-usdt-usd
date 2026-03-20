"""
Standalone script to test ABCEX USDT/RUB data fetching.
Run: python scripts/test_abcex.py
"""

import asyncio
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

BASE_URL = "https://hub.abcex.io/api"
INSTRUMENT = "USDTRUB"


async def fetch_json(session: AsyncSession, path: str, params: dict | None = None) -> dict | list:
    url = f"{BASE_URL}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    r = await session.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


async def main():
    async with AsyncSession(impersonate="chrome110") as session:
        ticker_data, orderbook, trades = await asyncio.gather(
            fetch_json(session, "/v2/exchange/public/candle/spot/ticker/day"),
            fetch_json(session, "/v2/exchange/public/orderbook/depth", {"instrumentCode": INSTRUMENT}),
            fetch_json(session, "/v2/exchange/public/trade/spot/list/recent", {"instrumentCode": INSTRUMENT}),
        )

        # === TICKER ===
        print("=" * 60)
        print(f"  ABCEX USDT/RUB - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        usdt_ticker = None
        tickers = ticker_data.get("tickers", []) if isinstance(ticker_data, dict) else []
        for t in tickers:
            if t.get("symbol") == INSTRUMENT:
                usdt_ticker = t
                break

        if usdt_ticker:
            print(f"\n{'TICKER':^60}")
            print("-" * 60)
            print(f"  Last price:   {usdt_ticker.get('lastPrice', '?')} RUB")
            print(f"  Bid (buy):    {usdt_ticker.get('bidPrice', '?')} RUB")
            print(f"  Ask (sell):   {usdt_ticker.get('askPrice', '?')} RUB")
            print(f"  High (24h):   {usdt_ticker.get('highPrice', '?')} RUB")
            print(f"  Low (24h):    {usdt_ticker.get('lowPrice', '?')} RUB")
            print(f"  Volume (24h): {usdt_ticker.get('quoteVolume', '?')} RUB")
            print(f"  Change:       {usdt_ticker.get('priceChangePercent', '?')}%")
        else:
            print("\n  [!] USDTRUB ticker not found in response")

        # === ORDERBOOK ===
        print(f"\n{'ORDERBOOK (TOP-10)':^60}")
        print("-" * 60)

        asks = orderbook.get("ask", [])[:10]
        bids = orderbook.get("bid", [])[:10]

        print(f"  {'ASK (sell)':^28} | {'BID (buy)':^28}")
        print(f"  {'Price':>10}  {'Qty USDT':>14} | {'Price':>10}  {'Qty USDT':>14}")
        print(f"  {'-'*28} | {'-'*28}")

        max_rows = max(len(asks), len(bids))
        for i in range(max_rows):
            ask_str = ""
            bid_str = ""
            if i < len(asks):
                a = asks[i]
                ask_str = f"  {float(a['price']):>10.2f}  {float(a['qty']):>14.2f}"
            else:
                ask_str = " " * 30
            if i < len(bids):
                b = bids[i]
                bid_str = f"  {float(b['price']):>10.2f}  {float(b['qty']):>14.2f}"
            else:
                bid_str = ""
            print(f"{ask_str} | {bid_str}")

        # === TRADES ===
        print(f"\n{'RECENT TRADES (last 10)':^60}")
        print("-" * 60)
        print(f"  {'Time':>10}  {'Side':>4}  {'Price':>8}  {'Qty USDT':>14}")
        print(f"  {'-'*42}")

        for trade in trades[:10]:
            price = float(trade["price"])
            qty = float(trade["qty"])
            side = trade.get("side", "?")
            ts_str = trade.get("updatedAt", "")
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                time_str = dt.astimezone().strftime("%H:%M:%S")
            except (ValueError, AttributeError):
                time_str = ts_str[:8] if ts_str else "?"
            side_display = "BUY" if side == "bid" else "SELL" if side == "ask" else side
            print(f"  {time_str:>10}  {side_display:>4}  {price:>8.2f}  {qty:>14.2f}")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
