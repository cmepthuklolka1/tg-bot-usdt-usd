"""Bounded Telegram HTML rendering. Truncation never splits an entity/tag."""

from datetime import timedelta, timezone
from html import escape, unescape

MOSCOW = timezone(timedelta(hours=3))


def units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def plain(text: str, limit: int = 100) -> str:
    # Item rows arrive HTML-escaped from the formatters, labels arrive plain.
    return escape(unescape(str(text))[:limit])


def render_report(report) -> str:
    unavailable = "временно недоступен"
    cbr = f"{report.cbrf_rate:.2f} ₽/$" if report.cbrf_rate else unavailable
    if report.cbrf_date:
        cbr += f" (на {report.cbrf_date:%d.%m.%Y})"
    abcex = " | ".join(f"{v:.2f} ₽" if v else "—" for v in (report.abcex_buy, report.abcex_sell)) if report.abcex_buy or report.abcex_sell else unavailable
    antarctic = f"{report.antarctic_onramp_rate:.2f} ₽ [{plain(report.antarctic_source, 70)}]" if report.antarctic_onramp_rate else unavailable
    owb = f"{report.owb_usdc_price:.5f} USDC" if report.owb_usdc_price else unavailable
    parts = [f"<b>{label}:</b> {value}" + (f" — {plain(report.source_notes[key], 100)}" if report.source_notes.get(key) else "")
             for key, label, value in [("cbrf", "Курс ЦБ РФ", cbr), ("abcex", "ABCEX", abcex), ("antarctic", "Antarctic", antarctic), ("uniswap", "UNISWAP OWB/USDC", owb)]]
    footer = f"<i>Проверено: {report.timestamp.astimezone(MOSCOW):%d.%m %H:%M:%S} МСК</i>"
    # Budget includes markup and UTF-16 surrogate pairs, stricter than Telegram.
    available = max(0, 3900 - units("\n".join(parts)) - units(footer))
    budget = max(100, available // max(1, len(report.sections)))
    for section in report.sections:
        label = f"<b>{plain(section.label, 95)}</b>"
        if not section.items:
            parts.append(label + "\n<i>Нет данных</i>")
            continue
        rows = []
        for pos, line in section.items:
            row = f"#{int(pos):<3}{plain(line, 75)}"
            if units(label + "\n<pre>" + "\n".join(rows + [row]) + "</pre>\n<i>Выдача сокращена</i>") > budget:
                break
            rows.append(row)
        body = label + "\n<pre>" + "\n".join(rows) + "</pre>"
        if len(rows) < len(section.items):
            body += "\n<i>Выдача сокращена</i>"
        parts.append(body)
    return "\n\n".join(parts + [footer])
