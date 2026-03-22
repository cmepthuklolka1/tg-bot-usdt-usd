from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any

# CBRF Model
class CBRFRate(BaseModel):
    date: datetime
    usd_rub: float = Field(..., gt=0)

# BestChange Model
class ExchangerOffer(BaseModel):
    exchanger_name: str
    give_rub: float
    get_usdt: float
    rate: float  # How many RUB for 1 USDT

class BestChangeRates(BaseModel):
    offers: list[ExchangerOffer]

# Bybit P2P Model
class P2PItem(BaseModel):
    id: str
    nickName: str
    price: float
    quantity: float      # Total USDT available from this seller
    minAmount: float
    maxAmount: float
    payments: list[str]

class BybitP2PResponsePayload(BaseModel):
    count: int
    items: list[P2PItem]

class BybitP2PResponse(BaseModel):
    retCode: int = Field(alias="ret_code")
    retMsg: str = Field(alias="ret_msg")
    result: BybitP2PResponsePayload

# Unified Presentation Model (what the UI will render)
class RateSection(BaseModel):
    label: str
    items: list[Any] = Field(default_factory=list)  # list of (position, formatted_line)

class ExchangeRateReport(BaseModel):
    cbrf_rate: float
    abcex_buy: float | None = None
    abcex_sell: float | None = None
    antarctic_onramp_rate: float | None = None
    owb_usdc_price: float | None = None
    sections: list[RateSection] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)

    def format_for_telegram(self) -> str:
        text = [
            f"<b>Курс ЦБ РФ:</b> {self.cbrf_rate:.2f} ₽/$",
        ]
        if self.abcex_buy is not None or self.abcex_sell is not None:
            buy_str = f"{self.abcex_buy:.2f}" if self.abcex_buy is not None else "—"
            sell_str = f"{self.abcex_sell:.2f}" if self.abcex_sell is not None else "—"
            text.append(f"<b>ABCEX:</b>  {buy_str} ₽ | {sell_str} ₽")
        if self.antarctic_onramp_rate is not None:
            text.append(f"<b>Antarctic:</b>  {self.antarctic_onramp_rate:.2f} ₽ [СБП]")
        if self.owb_usdc_price is not None:
            text.append(f"<b>UNISWAP OWB/USDC:</b> {self.owb_usdc_price:.5f} USDC")
        text.append("")

        for section in self.sections:
            text.append(f"<b>{section.label}</b>")
            if section.items:
                rows = [f"#{pos:<3}{line}" for pos, line in section.items]
                text.append("<pre>" + "\n".join(rows) + "</pre>")
            else:
                text.append("<i>Нет данных</i>")

        text.append(f"<i>Обновлено: {self.timestamp.strftime('%H:%M:%S')}</i>")
        return "\n".join(text)
