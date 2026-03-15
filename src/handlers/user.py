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


async def _get_actual_pinned_id(bot, chat_id: int) -> int | None:
    """Возвращает message_id реально закреплённого сообщения в Telegram, или None."""
    try:
        chat_info = await bot.get_chat(chat_id)
        if chat_info.pinned_message:
            return chat_info.pinned_message.message_id
    except Exception:
        pass
    return None


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
    stored_msg_id = pinned_storage.get_all().get(str(chat_id))

    # Проверяем, какое сообщение реально закреплено в Telegram
    actual_pinned_id = await _get_actual_pinned_id(callback.bot, chat_id)

    # Обновляем существующее, только если оно реально закреплено
    if stored_msg_id and actual_pinned_id == stored_msg_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=stored_msg_id,
                text="⏳ Загружаю данные с бирж...",
            )
            report_text = await generate_rates_report()
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=stored_msg_id,
                text=report_text,
                reply_markup=get_rates_keyboard(),
                parse_mode="HTML",
            )
            return
        except Exception as e:
            logger.warning(f"Не удалось обновить закреплённое сообщение {stored_msg_id}: {e}")

    # Stored ID устарел или отсутствует — очищаем и создаём новое
    if stored_msg_id:
        pinned_storage.remove_pinned(chat_id)

    # Отправляем новое сообщение и закрепляем
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

    chat_id = callback.message.chat.id
    try:
        await callback.message.edit_text("⏳ Обновляю данные с бирж...")
        report_text = await generate_rates_report()
        await callback.message.edit_text(
            text=report_text,
            reply_markup=get_rates_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        # Сообщение удалено или недоступно — создаём новое и закрепляем
        logger.warning(f"Сообщение с курсами недоступно ({chat_id}), создаём новое: {e}")
        pinned_storage = PinnedMessageStorage()
        pinned_storage.remove_pinned(chat_id)
        try:
            report_text = await generate_rates_report()
            sent = await callback.bot.send_message(
                chat_id=chat_id,
                text=report_text,
                reply_markup=get_rates_keyboard(),
                parse_mode="HTML",
            )
            try:
                await callback.bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=sent.message_id,
                    disable_notification=True,
                )
            except Exception:
                pass
            pinned_storage.set_pinned(chat_id, sent.message_id)
        except Exception as e2:
            logger.error(f"Не удалось создать новое сообщение с курсами: {e2}")


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
