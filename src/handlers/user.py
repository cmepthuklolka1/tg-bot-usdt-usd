import logging
import unicodedata
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..config import config
from ..domain.models import ExchangeRateReport
from ..keyboards.menus import (
    get_main_menu_keyboard, get_rates_keyboard,
    get_settings_exchange_keyboard, get_settings_mode_keyboard, get_settings_input_keyboard,
    get_settings_bc_menu_keyboard, get_settings_bc_payment_keyboard, get_settings_bc_coin_keyboard,
)
from ..services.cbrf import fetch_usd_rub_rate
from ..services.bestchange import fetch_bestchange_rates
from ..services.bybit_p2p import fetch_bybit_p2p_rates
from ..utils.storage import (
    WhitelistStorage, PinnedMessageStorage, UserSettingsStorage, DISPLAY_DEFAULTS,
)

router = Router()
logger = logging.getLogger(__name__)
storage = WhitelistStorage()
settings_storage = UserSettingsStorage()

EXCHANGE_LABELS = {
    "bestchange": "BestChange",
    "bybit": "Bybit P2P",
}

PAYMENT_SLUGS = {
    "sberbank":  "Сбер",
    "alfaclick": "Альфа-Банк",
    "tinkoff":   "Т-Банк",
    "vtb":       "ВТБ",
}

COIN_SLUGS = {
    "tether-erc20": "USDT ERC20",
    "tether-trc20": "USDT TRC20",
    "tether-bep20": "USDT BEP20",
    "tether-ton":   "USDT TON",
}


# ─── FSM States ───────────────────────────────────────────────

class SettingsStates(StatesGroup):
    choosing_bc_section = State()   # sub-меню BestChange: источник / выдача
    choosing_bc_payment = State()
    choosing_bc_coin = State()
    choosing_mode = State()
    waiting_for_value = State()


# ─── Helpers ──────────────────────────────────────────────────

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


def _format_bc_line(offer) -> str:
    name = _pad_to_width(offer.exchanger_name, 18)
    return f"{name} {offer.rate:>7.2f} ₽"


def _format_bybit_line(item) -> str:
    name = _pad_to_width(item.nickName, 18)
    return f"{name} {item.price:>7.2f} ₽"


def _apply_display_settings(items: list, settings: dict, format_fn) -> list[tuple[int, str]]:
    """Применяет настройки отображения (подряд / по номерам) к списку элементов.
    Возвращает список (номер_позиции, отформатированная_строка)."""
    mode = settings.get("mode", "sequential")
    value = settings.get("value", 10)

    if mode == "sequential":
        n = value if isinstance(value, int) else 10
        return [(i + 1, format_fn(item)) for i, item in enumerate(items[:n])]
    else:  # positions
        positions = value if isinstance(value, list) else [1]
        result = []
        for pos in sorted(positions):
            idx = pos - 1
            if 0 <= idx < len(items):
                result.append((pos, format_fn(items[idx])))
        return result


def _format_settings_text(user_id: int) -> str:
    """Форматирует текст с текущими настройками пользователя."""
    all_settings = settings_storage.get_all_settings(user_id)
    lines = ["<b>⚙️ Настройки отображения</b>\n"]
    for exchange, label in EXCHANGE_LABELS.items():
        s = all_settings[exchange]
        mode = s.get("mode", "sequential")
        value = s.get("value")
        if mode == "sequential":
            desc = f"первые {value}"
        else:
            desc = f"позиции {', '.join(str(v) for v in value)}"
        if exchange == "bestchange":
            payment = s.get("payment", "sberbank")
            coin = s.get("coin", "tether-bep20")
            pay_label = PAYMENT_SLUGS.get(payment, payment)
            coin_label = COIN_SLUGS.get(coin, coin)
            lines.append(f"<b>{label}:</b> {pay_label} → {coin_label}, {desc}")
        else:
            lines.append(f"<b>{label}:</b> {desc}")
    lines.append("\nВыберите биржу для настройки:")
    return "\n".join(lines)


def _format_bc_menu_text(user_id: int) -> str:
    """Форматирует текст суб-меню BestChange с текущими настройками."""
    s = settings_storage.get_exchange_settings(user_id, "bestchange")
    payment = s.get("payment", "sberbank")
    coin = s.get("coin", "tether-bep20")
    mode = s.get("mode", "positions")
    value = s.get("value", [1, 10])
    pay_label = PAYMENT_SLUGS.get(payment, payment)
    coin_label = COIN_SLUGS.get(coin, coin)
    if mode == "sequential":
        display_desc = f"первые {value}"
    else:
        display_desc = f"позиции {', '.join(str(v) for v in value)}"
    return (
        f"<b>📈 BestChange — настройки</b>\n\n"
        f"Источник: <b>{pay_label} → {coin_label}</b>\n"
        f"Выдача: <b>{display_desc}</b>\n\n"
        f"Что хотите изменить?"
    )


# ─── Report Generation ───────────────────────────────────────

async def generate_rates_report(user_id: int | None = None) -> str:
    """Fetches all rates and returns the formatted telegram message."""
    # Загружаем настройки пользователя
    if user_id:
        bc_settings = settings_storage.get_exchange_settings(user_id, "bestchange")
        by_settings = settings_storage.get_exchange_settings(user_id, "bybit")
    else:
        bc_settings = DISPLAY_DEFAULTS["bestchange"]
        by_settings = DISPLAY_DEFAULTS["bybit"]

    try:
        cbrf = await fetch_usd_rub_rate()
        cbrf_rate = cbrf.usd_rub
    except Exception as e:
        logger.error(f"Generate report CBRF error: {e}")
        cbrf_rate = 0.0

    bc_payment = bc_settings.get("payment", "sberbank")
    bc_coin = bc_settings.get("coin", "tether-bep20")

    bestchange_items: list[tuple[int, str]] = []
    try:
        bc = await fetch_bestchange_rates(payment=bc_payment, coin=bc_coin)
        bestchange_items = _apply_display_settings(bc.offers, bc_settings, _format_bc_line)
    except Exception as e:
        logger.error(f"Generate report BestChange error: {e}")

    pay_label = PAYMENT_SLUGS.get(bc_payment, bc_payment)
    coin_label = COIN_SLUGS.get(bc_coin, bc_coin)
    bc_label = f"BestChange ({pay_label} → {coin_label})"

    bybit_items: list[tuple[int, str]] = []
    try:
        bybit = await fetch_bybit_p2p_rates()
        bybit_items = _apply_display_settings(bybit, by_settings, _format_bybit_line)
    except Exception as e:
        logger.error(f"Generate report Bybit error: {e}")

    report = ExchangeRateReport(
        cbrf_rate=cbrf_rate,
        bestchange_label=bc_label,
        bestchange_items=bestchange_items,
        bybit_items=bybit_items,
        timestamp=datetime.now()
    )
    return report.format_for_telegram()


# ─── /start и /settings Commands ────────────────────────────

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


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    if not storage.is_allowed(message.from_user.id):
        await message.answer(
            "🔒 <b>Доступ ограничен</b>",
            parse_mode="HTML"
        )
        return

    await state.clear()
    text = _format_settings_text(message.from_user.id)
    await message.answer(text, reply_markup=get_settings_exchange_keyboard(), parse_mode="HTML")


# ─── Rates Handlers ──────────────────────────────────────────

@router.callback_query(F.data == "show_rates")
async def cb_show_rates(callback: CallbackQuery):
    if not storage.is_allowed(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer("Загружаю актуальные курсы...")

    pinned_storage = PinnedMessageStorage()
    chat_id = callback.message.chat.id
    old_msg_id = pinned_storage.get_all().get(str(chat_id))

    # Всегда отправляем новое сообщение (чтобы оно было внизу чата)
    try:
        sent = await callback.bot.send_message(
            chat_id=chat_id,
            text="⏳ Загружаю данные с бирж...",
        )
        report_text = await generate_rates_report(user_id=callback.from_user.id)
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
        # Удаляем старое сообщение с курсами (чтобы не было дубликатов)
        if old_msg_id:
            try:
                await callback.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
            except Exception:
                pass  # >48ч или уже удалено — не страшно
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
        report_text = await generate_rates_report(user_id=callback.from_user.id)
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
            report_text = await generate_rates_report(user_id=callback.from_user.id)
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
async def cb_back_to_main(callback: CallbackQuery, state: FSMContext):
    if not storage.is_allowed(callback.from_user.id):
        return

    await state.clear()
    await callback.answer()
    is_admin = callback.from_user.id == config.admin_id
    await callback.bot.send_message(
        chat_id=callback.message.chat.id,
        text="Главное меню:",
        reply_markup=get_main_menu_keyboard(is_admin),
    )


# ─── Settings Helpers ────────────────────────────────────────

async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup):
    """Редактирует текущее сообщение; если не получается — отправляет новое."""
    try:
        await callback.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


# ─── Settings Handlers ───────────────────────────────────────

@router.callback_query(F.data == "settings_menu")
async def cb_settings_menu(callback: CallbackQuery, state: FSMContext):
    if not storage.is_allowed(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    text = _format_settings_text(callback.from_user.id)
    await _edit_or_send(callback, text, get_settings_exchange_keyboard())


@router.callback_query(F.data.in_({"settings_bestchange", "settings_bybit"}))
async def cb_settings_exchange(callback: CallbackQuery, state: FSMContext):
    if not storage.is_allowed(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    exchange = "bestchange" if callback.data == "settings_bestchange" else "bybit"
    label = EXCHANGE_LABELS[exchange]

    # Сохраняем ID этого сообщения — в него будем редактировать после ввода текста
    await state.update_data(exchange=exchange, settings_msg_id=callback.message.message_id)
    await callback.answer()

    current = settings_storage.get_exchange_settings(callback.from_user.id, exchange)

    if exchange == "bestchange":
        # BestChange: показываем суб-меню с выбором раздела
        await state.set_state(SettingsStates.choosing_bc_section)
        await _edit_or_send(
            callback,
            _format_bc_menu_text(callback.from_user.id),
            get_settings_bc_menu_keyboard(),
        )
    else:
        # Bybit: сразу выбор режима
        mode = current.get("mode", "sequential")
        value = current.get("value")
        if mode == "sequential":
            current_desc = f"первые {value}"
        else:
            current_desc = f"позиции {', '.join(str(v) for v in value)}"
        await state.set_state(SettingsStates.choosing_mode)
        await _edit_or_send(
            callback,
            f"<b>{label}</b>\nТекущая настройка: {current_desc}\n\nВыберите режим отображения:",
            get_settings_mode_keyboard(),
        )


@router.callback_query(SettingsStates.choosing_bc_section, F.data.in_({"bc_section_source", "bc_section_display"}))
async def cb_settings_bc_section(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор раздела настроек BestChange: источник данных или выдача."""
    await callback.answer()
    current = settings_storage.get_exchange_settings(callback.from_user.id, "bestchange")

    if callback.data == "bc_section_source":
        # → выбор банка
        payment = current.get("payment", "sberbank")
        coin = current.get("coin", "tether-bep20")
        pay_label = PAYMENT_SLUGS.get(payment, payment)
        coin_label = COIN_SLUGS.get(coin, coin)
        await state.set_state(SettingsStates.choosing_bc_payment)
        await _edit_or_send(
            callback,
            f"<b>BestChange — источник данных</b>\nТекущий: {pay_label} → {coin_label}\n\nВыберите банк:",
            get_settings_bc_payment_keyboard(),
        )
    else:
        # → выбор режима выдачи
        mode = current.get("mode", "positions")
        value = current.get("value", [1, 10])
        current_desc = f"первые {value}" if mode == "sequential" else f"позиции {', '.join(str(v) for v in value)}"
        await state.set_state(SettingsStates.choosing_mode)
        await _edit_or_send(
            callback,
            f"<b>BestChange — выдача</b>\nТекущая настройка: {current_desc}\n\nВыберите режим отображения:",
            get_settings_mode_keyboard(),
        )


@router.callback_query(SettingsStates.choosing_bc_payment, F.data.startswith("bc_pay_"))
async def cb_settings_bc_payment(callback: CallbackQuery, state: FSMContext):
    payment = callback.data.removeprefix("bc_pay_")
    await state.update_data(payment=payment)
    await state.set_state(SettingsStates.choosing_bc_coin)
    await callback.answer()

    pay_label = PAYMENT_SLUGS.get(payment, payment)
    current = settings_storage.get_exchange_settings(callback.from_user.id, "bestchange")
    data = await state.get_data()
    coin = data.get("coin") or current.get("coin", "tether-bep20")
    coin_label = COIN_SLUGS.get(coin, coin)

    await _edit_or_send(
        callback,
        f"<b>BestChange — источник данных</b>\nБанк: {pay_label}\nТекущий актив: {coin_label}\n\nВыберите актив:",
        get_settings_bc_coin_keyboard(),
    )


@router.callback_query(SettingsStates.choosing_bc_coin, F.data.startswith("bc_coin_"))
async def cb_settings_bc_coin(callback: CallbackQuery, state: FSMContext):
    """Сохраняет источник данных (банк + монета) и возвращает в bc-меню."""
    coin = callback.data.removeprefix("bc_coin_")
    await callback.answer()

    data = await state.get_data()
    payment = data.get("payment", "sberbank")

    # Сохраняем только источник (payment+coin); mode/value берутся из существующих настроек
    existing = settings_storage.get_exchange_settings(callback.from_user.id, "bestchange")
    settings_storage.set_exchange_settings(
        callback.from_user.id, "bestchange",
        mode=existing.get("mode", "positions"),
        value=existing.get("value", [1, 10]),
        payment=payment, coin=coin,
    )

    pay_label = PAYMENT_SLUGS.get(payment, payment)
    coin_label = COIN_SLUGS.get(coin, coin)

    await state.set_state(SettingsStates.choosing_bc_section)
    await _edit_or_send(
        callback,
        f"✅ Источник сохранён: <b>{pay_label} → {coin_label}</b>\n\n"
        + _format_bc_menu_text(callback.from_user.id),
        get_settings_bc_menu_keyboard(),
    )


@router.callback_query(SettingsStates.choosing_mode, F.data.in_({"mode_sequential", "mode_positions"}))
async def cb_settings_mode(callback: CallbackQuery, state: FSMContext):
    mode = "sequential" if callback.data == "mode_sequential" else "positions"
    await state.update_data(mode=mode)
    await state.set_state(SettingsStates.waiting_for_value)
    await callback.answer()

    if mode == "sequential":
        prompt = "Введите количество первых строк для отображения.\nПример: <b>15</b>"
    else:
        prompt = "Введите номера позиций через запятую.\nПример: <b>1, 3, 5, 7</b>"

    await _edit_or_send(callback, prompt, get_settings_input_keyboard())


@router.message(SettingsStates.waiting_for_value)
async def process_settings_value(message: Message, state: FSMContext):
    if not message.text:
        return

    data = await state.get_data()
    exchange = data.get("exchange", "bybit")
    mode = data.get("mode", "sequential")
    label = EXCHANGE_LABELS.get(exchange, exchange)
    settings_msg_id = data.get("settings_msg_id")

    # Удаляем сообщение пользователя (убираем мусор из чата)
    try:
        await message.delete()
    except Exception:
        pass

    text = message.text.strip()

    async def show_error(err: str):
        """Редактирует сообщение с настройками, показывая ошибку + промпт снова."""
        if mode == "sequential":
            prompt = "Введите количество первых строк для отображения.\nПример: <b>15</b>"
        else:
            prompt = "Введите номера позиций через запятую.\nПример: <b>1, 3, 5, 7</b>"
        full = f"{err}\n\n{prompt}"
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=settings_msg_id,
                text=full,
                reply_markup=get_settings_input_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            await message.answer(err, reply_markup=get_settings_input_keyboard(), parse_mode="HTML")

    payment = data.get("payment")  # None для Bybit
    coin = data.get("coin")        # None для Bybit

    if mode == "sequential":
        if not text.isdigit() or int(text) < 1:
            await show_error("❌ Введите положительное число (например: <b>10</b>).")
            return
        value = int(text)
        if value > 50:
            await show_error("❌ Максимум — 50.")
            return
        settings_storage.set_exchange_settings(message.from_user.id, exchange, mode, value,
                                               payment=payment, coin=coin)
        desc = f"первые {value}"
    else:  # positions
        cleaned = text.replace(" ", "")
        parts = [p for p in cleaned.split(",") if p]
        if not parts:
            await show_error("❌ Неверный формат. Введите номера через запятую (например: <b>1, 3, 5, 7</b>).")
            return
        if not all(p.isdigit() and int(p) >= 1 for p in parts):
            await show_error("❌ Все номера должны быть положительными числами.\nПример: <b>1, 3, 5, 7</b>")
            return
        value = sorted(set(int(p) for p in parts))
        if any(v > 100 for v in value):
            await show_error("❌ Номер позиции не может быть больше 100.")
            return
        settings_storage.set_exchange_settings(message.from_user.id, exchange, mode, value,
                                               payment=payment, coin=coin)
        desc = f"позиции {', '.join(str(v) for v in value)}"

    # После сохранения: BestChange → bc-меню, Bybit → главные настройки
    if exchange == "bestchange":
        await state.set_state(SettingsStates.choosing_bc_section)
        confirm_text = f"✅ Выдача сохранена: <b>{desc}</b>\n\n" + _format_bc_menu_text(message.from_user.id)
        reply_markup = get_settings_bc_menu_keyboard()
    else:
        await state.clear()
        confirm_text = f"✅ <b>{label}</b> — настроено: {desc}\n\n" + _format_settings_text(message.from_user.id)
        reply_markup = get_settings_exchange_keyboard()

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=settings_msg_id,
            text=confirm_text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(
            confirm_text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
