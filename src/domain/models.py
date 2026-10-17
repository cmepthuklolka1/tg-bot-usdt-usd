from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Any, Annotated

PositivePrice = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonnegativeAmount = Annotated[float, Field(ge=0, allow_inf_nan=False)]

# CBRF Model
class CBRFRate(BaseModel):
    date: datetime
    usd_rub: PositivePrice

# BestChange Model
class ExchangerOffer(BaseModel):
    exchanger_name: str
    give_rub: PositivePrice
    get_usdt: PositivePrice
    rate: PositivePrice

class BestChangeRates(BaseModel):
    offers: list[ExchangerOffer]

# Bybit P2P Model
class P2PItem(BaseModel):
    id: str
    nickName: str
    price: PositivePrice
    quantity: NonnegativeAmount
    minAmount: NonnegativeAmount
    maxAmount: NonnegativeAmount
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
    cbrf_rate: PositivePrice | None = None
    cbrf_date: datetime | None = None
    abcex_buy: PositivePrice | None = None
    abcex_sell: PositivePrice | None = None
    antarctic_onramp_rate: PositivePrice | None = None
    antarctic_source: str = "пополнение"
    owb_usdc_price: PositivePrice | None = None
    source_notes: dict[str, str] = Field(default_factory=dict)
    sections: list[RateSection] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def format_for_telegram(self) -> str:
        from .render import render_report
        return render_report(self)
