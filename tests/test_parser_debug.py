import asyncio
import bs4
from curl_cffi.requests import AsyncSession

async def run_bybit():
    print("--- Testing Bybit ---")
    import src.services.bybit_p2p as bybit
    session = AsyncSession(impersonate='chrome110')
    res = await session.post(bybit.URL, headers=bybit.HEADERS, json=bybit.PAYLOAD)
    print("Status:", res.status_code)
    print("JSON keys:", res.json().keys() if res.status_code == 200 else "Failed")
    if res.status_code == 200:
        data = res.json()
        print("ret_code:", data.get('ret_code'))
        print("retCode:", data.get('retCode'))
    await session.close()

async def run_bestchange():
    print("\n--- Testing BestChange ---")
    session = AsyncSession(impersonate='chrome110')
    
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    res = await session.get('https://www.bestchange.ru/sberbank-to-tether-bep20.html', headers=headers)
    print("Status:", res.status_code, "Length:", len(res.content))
    
    soup = bs4.BeautifulSoup(res.content, 'html.parser')
    tables = soup.find_all('table')
    print("Table IDs found:", [t.get('id') for t in tables])
    
    content_table = soup.find('table', id='content_table')
    if content_table:
        tbody = content_table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr', recursive=False)
            print(f"Found {len(rows)} rows in tbody")
            if len(rows) > 0:
                print("First row classes:", rows[0].get('class'))
        else:
            print("Found content_table, but no tbody!")
    else:
        print("Could NOT find content_table!")
        
    await session.close()

async def main():
    await run_bybit()
    await run_bestchange()

if __name__ == "__main__":
    asyncio.run(main())
