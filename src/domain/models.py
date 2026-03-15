from datetime import datetime
from pydantic import BaseModel, Field

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
    bestchange_top_1: str | None = None
    bestchange_top_10: str | None = None
    bybit_items: list[str] = Field(default_factory=list)  # Up to 7 items
    timestamp: datetime = Field(default_factory=datetime.now)

    def format_for_telegram(self) -> str:
        text = [
            f"<b>Курс ЦБ РФ:</b> {self.cbrf_rate:.2f} ₽/$",
            "",
            "<b>BestChange (Сбер → USDT BEP20)</b>",
        ]

        bc_rows = []
        if self.bestchange_top_1:
            bc_rows.append(f"#1  {self.bestchange_top_1}")
        if self.bestchange_top_10:
            bc_rows.append(f"#10 {self.bestchange_top_10}")
        if bc_rows:
            text.append("<pre>" + "\n".join(bc_rows) + "</pre>")

        text.append("<b>Bybit P2P (USDT/RUB)</b>")

        if self.bybit_items:
            bybit_rows = [
                f"#{i:<2} {line}"
                for i, line in enumerate(self.bybit_items, start=1)
            ]
            text.append("<pre>" + "\n".join(bybit_rows) + "</pre>")
        else:
            text.append("<i>Нет данных</i>")

        text.append(f"<i>Обновлено: {self.timestamp.strftime('%H:%M:%S')}</i>")
        return "\n".join(text)
