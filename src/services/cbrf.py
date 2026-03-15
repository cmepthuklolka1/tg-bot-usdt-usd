import xml.etree.ElementTree as ET
from datetime import datetime
import logging
from curl_cffi.requests import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from ..domain.models import CBRFRate

logger = logging.getLogger(__name__)

URL = "https://www.cbr.ru/scripts/XML_daily.asp"
# CBRF expects a normal user-agent, curl_cffi provides it automatically
# But it's good practice to set it explicitly
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def fetch_usd_rub_rate() -> CBRFRate:
    """Fetches official USD/RUB exchange rate from CBRF."""
    session = AsyncSession(impersonate="chrome110")
    try:
        response = await session.get(URL, headers=HEADERS, timeout=10)
        response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.content)
        date_str = root.attrib.get('Date', '')
        date_obj = datetime.strptime(date_str, "%d.%m.%Y") if date_str else datetime.now()

        # Find USD (ID = R01235)
        usd_element = root.find(".//Valute[@ID='R01235']")
        if usd_element is None:
            raise ValueError("USD rate (R01235) not found in CBRF XML.")

        value_str = usd_element.findtext("Value")
        if not value_str:
            raise ValueError("USD Value node is empty.")

        # CBRF uses comma for decimals
        value_float = float(value_str.replace(',', '.'))
        
        return CBRFRate(date=date_obj, usd_rub=value_float)

    except Exception as e:
        logger.error(f"Failed to fetch CBRF rate: {e}")
        raise
    finally:
        await session.close()
