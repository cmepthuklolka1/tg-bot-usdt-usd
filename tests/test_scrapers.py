import asyncio
from src.services.cbrf import fetch_usd_rub_rate
from src.services.bestchange import fetch_bestchange_rates
from src.services.bybit_p2p import fetch_bybit_p2p_rates

async def main():
    print("--- [1] Testing CBRF ---")
    try:
        cbrf = await fetch_usd_rub_rate()
        print(f"Success CBRF: {cbrf.usd_rub} RUB on {cbrf.date}")
    except Exception as e:
        print(f"Error CBRF: {e}")

    print("\n--- [2] Testing BestChange ---")
    try:
        bc_rates = await fetch_bestchange_rates()
        for i, offer in enumerate(bc_rates.offers):
            print(f"Offer {i+1}: {offer.exchanger_name} | {offer.give_rub} RUB -> {offer.get_usdt} USDT | Rate: {offer.rate}")
    except Exception as e:
        print(f"Error BestChange: {e}")

    print("\n--- [3] Testing ByBit P2P ---")
    try:
        bybit_items = await fetch_bybit_p2p_rates()
        for i, item in enumerate(bybit_items[:7]):
            stock_rub = item.quantity * item.price
            print(f"Item {i+1}: {item.nickName} | Price: {item.price} | Stock: ~{stock_rub:.0f} RUB")
    except Exception as e:
        print(f"Error ByBit: {e}")

if __name__ == "__main__":
    asyncio.run(main())
