import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
from ..utils.http import shared_session, check_response, request_timeout

from ..domain.models import CBRFRate
from ..utils.retry import CBRF_RETRY

logger = logging.getLogger(__name__)

URL = "https://www.cbr.ru/scripts/XML_daily.asp"
MIRROR_URL = "https://www.cbr-xml-daily.ru/daily_utf8.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@CBRF_RETRY
async def _fetch_rate(endpoint, url):
    async with shared_session() as session:
        response = await session.get(url, headers=HEADERS, timeout=request_timeout())
        check_response(response)

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            raise ValueError("Invalid CBRF XML") from error
        if root.tag != "ValCurs":
            raise ValueError("Unexpected CBRF XML root")
        date_obj = datetime.strptime(root.attrib.get("Date", ""), "%d.%m.%Y")

        usd_element = root.find(".//Valute[@ID='R01235']")
        if usd_element is None:
            raise ValueError("USD rate (R01235) not found in CBRF XML.")

        value_str = usd_element.findtext("Value")
        if not value_str:
            raise ValueError("USD Value node is empty.")

        nominal = int(usd_element.findtext("Nominal", ""))
        if nominal <= 0:
            raise ValueError("USD Nominal must be positive")
        value_float = float(value_str.replace(',', '.')) / nominal
        return endpoint, CBRFRate(date=date_obj, usd_rub=value_float)


async def fetch_usd_rub_rate() -> CBRFRate:
    """Race independent HTTPS endpoints; only a validated rate can win."""
    tasks = [asyncio.create_task(_fetch_rate(endpoint, url)) for endpoint, url in
             (("direct", URL), ("mirror", MIRROR_URL))]
    errors = []
    try:
        for completed in asyncio.as_completed(tasks):
            try:
                endpoint, rate = await completed
            except Exception as error:
                errors.append(error)
                continue
            logger.info("source=cbrf endpoint=%s event=selected rate_date=%s", endpoint, rate.date.date())
            return rate
        raise errors[-1]
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
