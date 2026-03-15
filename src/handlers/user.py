import logging
import unicodedata
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from ..config import config
from ..domain.models import ExchangeRateReport
from ..keyboards.menus import get_main_menu_keyboard, get_rates_keyboard
from ..services.cbrf import fetch_usd_rub_rate
from ..services.bestchange import fetch_bestchange_rates
from ..services.bybit_p2p import fetch_bybit_p2p_rates
from ..utils.storage import WhitelistStorage, PinnedMessageStorage

router = Router()
logger = logging.getLogger(__name__)
storage = WhitelistStorage()


def _pad_to_width(s: str, width: int) -> str:
    """Обрезает строку до визуальной ширины width и добивает пробелами.
    Emoji и иероглифы ('W', 'F') = 2 единицы, остальные символы = 1."""
    current_w = 0
    result = []
    for char in s:
        char_w = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
        if current_w + char_w > width:
            break
        result.append(char)
        current_w += char_w
    result.append(' ' * (width - current_w))
    return ''.join(result)

async def generate_rates_report() -> str:
    """Fetches all rates and returns the formatted telegram message."""
    try:
        cbrf = await fetch_usd_rub_rate()
        cbrf_rate = cbrf.usd_rub
    except Exception as e:
        logger.error(f"Generate report CBRF error: {e}")
        cbrf_rate = 0.0

    bestchange_1 = None
    bestchange_10 = None
    try:
        bc = await fetch_bestchange_rates()
        if len(bc.offers) > 0:
            name = _pad_to_width(bc.offers[0].exchanger_name, 18)
            bestchange_1 = f"{name} {bc.offers[0].rate:>7.2f} ₽"
        if len(bc.offers) >= 2:
            name = _pad_to_width(bc.offers[1].exchanger_name, 18)
            bestchange_10 = f"{name} {bc.offers[1].rate:>7.2f} ₽"
    except Exception as e:
        logger.error(f"Generate report BestChange error: {e}")

    bybit_lines: list[str] = []
    try:
        bybit = await fetch_bybit_p2p_rates()
        for item in bybit[:10]:
            name = _pad_to_width(item.nickName, 18)
            bybit_lines.append(f"{name} {item.price:>7.2f} ₽")
    except Exception as e:
        logger.error(f"Generate report Bybit error: {e}")

    report = ExchangeRateReport(
        cbrf_rate=cbrf_rate,
        bestchange_top_1=bestchange_1,
        bestchange_top_10=bestchange_10,
        bybit_items=bybit_lines,
        timestamp=datetime.now()
    )
    return report.format_for_telegram()

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not storage.is_allowed(message.from_user.id):
        await message.answer(
            "🔒 <b>Доступ ограничен</b>\n\n"
            "Этот бот является приватным. У вас нет доступа к нему.\n"
            "Если вы считаете, что это ошибка — обратитесь к администратору.",
            parse_mode="HTML"
        )
        return

    is_admin = message.from_user.id == config.admin_id
    text = "Привет! Я приватный бот для мониторинга курсов USD/USDT.\nВыберите нужное действие в меню ниже:"
    await message.answer(text, reply_markup=get_main_menu_keyboard(is_admin))


@router.callback_query(F.data == "show_rates")
async def cb_show_rates(callback: CallbackQuery):
    if not storage.is_allowed(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer("Загружаю актуальные курсы...")

    pinned_storage = PinnedMessageStorage()
    chat_id = callback.message.chat.id
    existing_msg_id = pinned_storage.get_all().get(str(chat_id))

    # Если уже есть закреплённое сообщение с курсами — обновляем его
    if existing_msg_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing_msg_id,
                text="⏳ Загружаю данные с бирж...",
            )
            report_text = await generate_rates_report()
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=existing_msg_id,
                text=report_text,
                reply_markup=get_rates_keyboard(),
                parse_mode="HTML",
            )
            return
        except Exception as e:
            logger.warning(f"Не удалось обновить закреплённое сообщение {existing_msg_id}: {e}")
            pinned_storage.remove_pinned(chat_id)

    # Нет закреплённого сообщения (или оно было удалено) — отправляем новое
    try:
        sent = await callback.bot.send_message(
            chat_id=chat_id,
            text="⏳ Загружаю данные с бирж...",
        )
        report_text = await generate_rates_report()
        await callback.bot.edit_message_text(
            chat_id=chat_id,
            message_id=sent.message_id,
            text=report_text,
            reply_markup=get_rates_keyboard(),
            parse_mode="HTML",
        )
        # Закрепляем в чате
        try:
            await callback.bot.pin_chat_message(
                chat_id=chat_id,
                message_id=sent.message_id,
                disable_notification=True,
            )
        except Exception as e:
            logger.warning(f"Не удалось закрепить сообщение для {chat_id}: {e}")
        pinned_storage.set_pinned(chat_id, sent.message_id)
    except Exception as e:
        logger.error(f"Ошибка отправки курсов: {e}")
        await callback.bot.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при получении данных.",
        )


@router.callback_query(F.data == "refresh_rates")
async def cb_refresh_rates(callback: CallbackQuery):
    if not storage.is_allowed(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer("Обновляю курсы...")

    try:
        await callback.message.edit_text("⏳ Обновляю данные с бирж...")
        report_text = await generate_rates_report()
        await callback.message.edit_text(
            text=report_text,
            reply_markup=get_rates_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка обновления курсов: {e}")
        await callback.answer("Ошибка при обновлении.", show_alert=True)


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    if not storage.is_allowed(callback.from_user.id):
        return

    await callback.answer()
    is_admin = callback.from_user.id == config.admin_id
    await callback.bot.send_message(
        chat_id=callback.message.chat.id,
        text="Главное меню:",
        reply_markup=get_main_menu_keyboard(is_admin),
    )
