import logging
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from ..domain.models import ExchangerOffer, BestChangeRates

logger = logging.getLogger(__name__)

# Target: Sberbank to USDT BEP20
URL = "https://www.bestchange.ru/sberbank-to-tether-bep20.html"

# We must mock a real browser to avoid Cloudflare JS challenges
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

def clean_float(text: str) -> float:
    """Helper to convert string like '100.50' or '100,50' or '100 000.5' to float."""
    # Remove spaces and non-breaking spaces
    clean = text.replace(' ', '').replace('\xa0', '')
    # BestChange usually uses periods for decimals, but just in case
    clean = clean.replace(',', '.')
    return float(clean)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=15))
async def fetch_bestchange_rates() -> BestChangeRates:
    """Scrapes 1st and 10th rows from BestChange's exchange table."""
    session = AsyncSession(impersonate="chrome110")
    try:
        response = await session.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # The main exchange table on bestchange has id="content_table"
        table = soup.find('table', id='content_table')
        if not table:
            raise ValueError("BestChange table 'content_table' not found.")
            
        tbody = table.find('tbody')
        if not tbody:
            raise ValueError("BestChange table <tbody> not found.")
            
        # Extract rows, ignoring hidden or header rows
        # Bestchange uses .odd and .even classes for regular rows
        rows = tbody.find_all('tr', recursive=False)
        
        valid_offers = []
        for row in rows:
            # Rows might not have classes, let's just attempt extraction
            tds = row.find_all('td')
            if len(tds) < 4:
                continue
                
            # Column 1: Exchanger name
            # The .bj div contains an <a> tag with the name, followed by <span> tooltip badges.
            # We take only the <a> tag text to avoid tooltip pollution.
            name_div = tds[1].find('div', class_='bj')
            if name_div:
                name_link = name_div.find('a')
                exchanger_name = name_link.text.strip() if name_link else name_div.contents[0].strip() if name_div.contents else ""
            else:
                # Fallback: first line of text
                exchanger_name = tds[1].get_text(separator='\n').split('\n')[0].strip()
                
            if not exchanger_name:
                continue
            
            # Column 2: Give (RUB)
            give_td = tds[2]
            give_fs = give_td.find('div', class_='fs')
            give_text = give_fs.text if give_fs else give_td.text
            # Remove badging like "Сбербанк RUB"
            give_text = give_text.split('Сбербанк')[0].split('RUB')[0].strip()
            
            # Column 3: Get (USDT)
            get_td = tds[3]
            get_fs = get_td.find('div', class_='fs')
            get_text = get_fs.text if get_fs else get_td.text
            get_text = get_text.split('USDT')[0].strip()
            
            try:
                give_val = clean_float(give_text)
                get_val = clean_float(get_text)
                
                valid_offers.append(
                    ExchangerOffer(
                        exchanger_name=exchanger_name,
                        give_rub=give_val,
                        get_usdt=get_val,
                        rate=give_val / get_val if get_val > 0 else 0
                    )
                )
            except ValueError:
                continue # Skip rows that couldn't be parsed

        logger.info(f"BestChange: {len(valid_offers)} valid offers parsed")
        return BestChangeRates(offers=valid_offers)

    except Exception as e:
        logger.error(f"Failed to fetch BestChange rates: {e}")
        raise
    finally:
        await session.close()
