import xml.etree.ElementTree as ET
from datetime import datetime
import logging
from curl_cffi.requests import AsyncSession

from ..domain.models import CBRFRate
from ..utils.retry import CBRF_RETRY

logger = logging.getLogger(__name__)

URL = "https://www.cbr.ru/scripts/XML_daily.asp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@CBRF_RETRY
async def fetch_usd_rub_rate() -> CBRFRate:
    """Fetches official USD/RUB exchange rate from CBRF."""
    async with AsyncSession(impersonate="chrome110") as session:
        response = await session.get(URL, headers=HEADERS, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        date_str = root.attrib.get('Date', '')
        date_obj = datetime.strptime(date_str, "%d.%m.%Y") if date_str else datetime.now()

        usd_element = root.find(".//Valute[@ID='R01235']")
        if usd_element is None:
            raise ValueError("USD rate (R01235) not found in CBRF XML.")

        value_str = usd_element.findtext("Value")
        if not value_str:
            raise ValueError("USD Value node is empty.")

        value_float = float(value_str.replace(',', '.'))
        return CBRFRate(date=date_obj, usd_rub=value_float)
