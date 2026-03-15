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
class ExchangeRateReport(BaseModel):
    cbrf_rate: float
    bestchange_label: str = "BestChange (Сбер → USDT BEP20)"
    bybit_label: str = "Bybit P2P (USDT/RUB)"
    bestchange_items: list[Any] = Field(default_factory=list)  # list of (position, formatted_line)
    bybit_items: list[Any] = Field(default_factory=list)       # list of (position, formatted_line)
    timestamp: datetime = Field(default_factory=datetime.now)

    def format_for_telegram(self) -> str:
        text = [
            f"<b>Курс ЦБ РФ:</b> {self.cbrf_rate:.2f} ₽/$",
            "",
            f"<b>{self.bestchange_label}</b>",
        ]

        if self.bestchange_items:
            bc_rows = [f"#{pos}  {line}" for pos, line in self.bestchange_items]
            text.append("\n".join(bc_rows))
        else:
            text.append("<i>Нет данных</i>")

        text.append(f"<b>{self.bybit_label}</b>")

        if self.bybit_items:
            bybit_rows = [f"#{pos}  {line}" for pos, line in self.bybit_items]
            text.append("\n".join(bybit_rows))
        else:
            text.append("<i>Нет данных</i>")

        text.append(f"<i>Обновлено: {self.timestamp.strftime('%H:%M:%S')}</i>")
        return "\n".join(text)
