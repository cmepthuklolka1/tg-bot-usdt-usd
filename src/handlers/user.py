import logging
from aiogram import Router, F
from aiogram.enums import ContentType
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..config import config
from ..keyboards.menus import (
    get_main_menu_keyboard,
    get_settings_exchange_keyboard, get_settings_mode_keyboard, get_settings_input_keyboard,
    get_settings_bc_menu_keyboard, get_settings_bc_payment_keyboard, get_settings_bc_coin_keyboard,
    get_settings_bybit_menu_keyboard, get_settings_bybit_amount_keyboard,
)
from ..services.reports import _format_amount_label, _format_bc_line, _format_bybit_line, _apply_display_settings
from ..utils.storage import (
    WhitelistStorage, PinnedMessageStorage, UserSettingsStorage, DISPLAY_DEFAULTS,
)

from .access import AccessMiddleware

router = Router()
router.message.outer_middleware(AccessMiddleware())
router.callback_query.outer_middleware(AccessMiddleware())
logger = logging.getLogger(__name__)
storage = WhitelistStorage()
settings_storage = UserSettingsStorage()


@router.message(F.content_type == ContentType.PINNED_MESSAGE)
async def delete_pin_notification(message: Message):
    """Удаляет служебное сообщение 'закрепил сообщение'."""
    logger.info("Pin notification received: chat=%s msg_id=%s", message.chat.id, message.message_id)
    try:
        await message.delete()
        logger.info("Pin notification deleted: msg_id=%s", message.message_id)
    except Exception as e:
        logger.warning("Failed to delete pin notification msg_id=%s: %s", message.message_id, e)

EXCHANGE_LABELS = {
    "bestchange_1": "BestChange-1",
    "bestchange_2": "BestChange-2",
    "bybit_1": "Bybit P2P-1",
    "bybit_2": "Bybit P2P-2",
}

PAYMENT_SLUGS = {
    "sberbank":  "Сбер",
    "alfaclick": "Альфа-Банк",
    "tinkoff":   "Т-Банк",
    "vtb":       "ВТБ",
}

COIN_SLUGS = {
    "tether-erc20": "USD\u200bT ERC20",
    "tether-trc20": "USD\u200bT TRC20",
    "tether-bep20": "USD\u200bT BEP20",
    "tether-ton":   "USD\u200bT TON",
}


# ─── FSM States ───────────────────────────────────────────────

class SettingsStates(StatesGroup):
    choosing_bc_section = State()      # sub-меню BestChange: источник / выдача
    choosing_bc_payment = State()
    choosing_bc_coin = State()
    choosing_bybit_section = State()   # sub-меню Bybit: сумма сделки / выдача
    waiting_for_bybit_amount = State() # ввод произвольной суммы Bybit
    choosing_mode = State()
    waiting_for_value = State()


# ─── Helpers ──────────────────────────────────────────────────

def _is_bc(exchange: str) -> bool:
    return exchange.startswith("bestchange")

def _is_bybit(exchange: str) -> bool:
    return exchange.startswith("bybit")


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
        if _is_bc(exchange):
            payment = s.get("payment", "sberbank")
            coin = s.get("coin", "tether-bep20")
            pay_label = PAYMENT_SLUGS.get(payment, payment)
            coin_label = COIN_SLUGS.get(coin, coin)
            lines.append(f"<b>{label}:</b> {pay_label} → {coin_label}, {desc}")
        elif _is_bybit(exchange):
            max_amount = s.get("max_amount", 100000)
            amount_label = _format_amount_label(max_amount)
            lines.append(f"<b>{label}:</b> [{amount_label}], {desc}")
    lines.append("\nВыберите биржу для настройки:")
    return "\n".join(lines)


def _format_bc_menu_text(user_id: int, exchange: str) -> str:
    """Форматирует текст суб-меню BestChange с текущими настройками."""
    label = EXCHANGE_LABELS.get(exchange, exchange)
    s = settings_storage.get_exchange_settings(user_id, exchange)
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
        f"<b>📈 {label} — настройки</b>\n\n"
        f"Источник: <b>{pay_label} → {coin_label}</b>\n"
        f"Выдача: <b>{display_desc}</b>\n\n"
        f"Что хотите изменить?"
    )


def _format_bybit_menu_text(user_id: int, exchange: str) -> str:
    """Форматирует текст суб-меню Bybit P2P с текущими настройками."""
    label = EXCHANGE_LABELS.get(exchange, exchange)
    s = settings_storage.get_exchange_settings(user_id, exchange)
    max_amount = s.get("max_amount", 100000)
    mode = s.get("mode", "sequential")
    value = s.get("value", 10)
    amount_label = _format_amount_label(max_amount)
    if mode == "sequential":
        display_desc = f"первые {value}"
    else:
        display_desc = f"позиции {', '.join(str(v) for v in value)}"
    return (
        f"<b>💰 {label} — настройки</b>\n\n"
        f"Сумма сделки: <b>{amount_label}</b>\n"
        f"Выдача: <b>{display_desc}</b>\n\n"
        f"Что хотите изменить?"
    )


# ─── Report Generation ───────────────────────────────────────

async def generate_rates_report(user_id: int | None = None) -> str:
    from ..services.reports import generate_rates_report as build_report
    return await build_report(user_id)


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
    text = "Привет! Я приватный бот для мониторинга курсов USD/USD\u200bT.\nВыберите нужное действие в меню ниже:"
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

@router.callback_query(F.data.in_({"show_rates", "refresh_rates"}))
async def cb_show_rates(callback: CallbackQuery):
    await callback.answer("Обновляю курсы…")
    from ..services.publishing import publisher
    try:
        text = await generate_rates_report(callback.from_user.id)
        published = await publisher.update(callback.bot, callback.message.chat.id, text,
                                           message_id=callback.message.message_id)
    except Exception as error:
        logger.warning("source=report_action error_kind=%s", type(error).__name__)
        published = False
    if not published:
        logger.warning("source=telegram event=report_update_deferred")
        await callback.message.answer("⚠️ Не удалось завершить обновление курсов. Попробуйте ещё раз.")
    else:
        logger.info("source=telegram event=report_displayed action=%s", callback.data)


# Keep a stable import for integrations calling the previous handler directly.
cb_refresh_rates = cb_show_rates


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery, state: FSMContext):
    if not storage.is_allowed(callback.from_user.id):
        return

    await state.clear()
    await callback.answer()
    is_admin = callback.from_user.id == config.admin_id

    # Если кнопка нажата в закреплённом сообщении с курсами — создаём новое,
    # иначе — редактируем текущее сообщение на месте.
    chat_id = callback.message.chat.id
    pinned_storage = PinnedMessageStorage()
    pinned_msg_id = pinned_storage.get_all().get(str(chat_id))

    if pinned_msg_id == callback.message.message_id:
        await callback.bot.send_message(
            chat_id=chat_id,
            text="Главное меню:",
            reply_markup=get_main_menu_keyboard(is_admin),
        )
    else:
        await _edit_or_send(
            callback,
            "Главное меню:",
            get_main_menu_keyboard(is_admin),
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


@router.callback_query(F.data.in_({"settings_bestchange_1", "settings_bestchange_2", "settings_bybit_1", "settings_bybit_2"}))
async def cb_settings_exchange(callback: CallbackQuery, state: FSMContext):
    if not storage.is_allowed(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    exchange = callback.data.removeprefix("settings_")

    # Сохраняем ID этого сообщения — в него будем редактировать после ввода текста
    await state.update_data(exchange=exchange, settings_msg_id=callback.message.message_id)
    await callback.answer()

    if _is_bc(exchange):
        # BestChange: показываем суб-меню с выбором раздела
        await state.set_state(SettingsStates.choosing_bc_section)
        await _edit_or_send(
            callback,
            _format_bc_menu_text(callback.from_user.id, exchange),
            get_settings_bc_menu_keyboard(),
        )
    elif _is_bybit(exchange):
        # Bybit: показываем суб-меню с выбором раздела
        await state.set_state(SettingsStates.choosing_bybit_section)
        await _edit_or_send(
            callback,
            _format_bybit_menu_text(callback.from_user.id, exchange),
            get_settings_bybit_menu_keyboard(),
        )


@router.callback_query(SettingsStates.choosing_bc_section, F.data.in_({"bc_section_source", "bc_section_display"}))
async def cb_settings_bc_section(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор раздела настроек BestChange: источник данных или выдача."""
    await callback.answer()
    data = await state.get_data()
    exchange = data.get("exchange", "bestchange_1")
    current = settings_storage.get_exchange_settings(callback.from_user.id, exchange)

    if callback.data == "bc_section_source":
        # → выбор банка
        payment = current.get("payment", "sberbank")
        coin = current.get("coin", "tether-bep20")
        pay_label = PAYMENT_SLUGS.get(payment, payment)
        coin_label = COIN_SLUGS.get(coin, coin)
        label = EXCHANGE_LABELS.get(exchange, exchange)
        await state.set_state(SettingsStates.choosing_bc_payment)
        await _edit_or_send(
            callback,
            f"<b>{label} — источник данных</b>\nТекущий: {pay_label} → {coin_label}\n\nВыберите банк:",
            get_settings_bc_payment_keyboard(),
        )
    else:
        # → выбор режима выдачи
        mode = current.get("mode", "positions")
        value = current.get("value", [1, 10])
        current_desc = f"первые {value}" if mode == "sequential" else f"позиции {', '.join(str(v) for v in value)}"
        label = EXCHANGE_LABELS.get(exchange, exchange)
        await state.set_state(SettingsStates.choosing_mode)
        await _edit_or_send(
            callback,
            f"<b>{label} — выдача</b>\nТекущая настройка: {current_desc}\n\nВыберите режим отображения:",
            get_settings_mode_keyboard(),
        )


@router.callback_query(SettingsStates.choosing_bc_payment, F.data.startswith("bc_pay_"))
async def cb_settings_bc_payment(callback: CallbackQuery, state: FSMContext):
    payment = callback.data.removeprefix("bc_pay_")
    await state.update_data(payment=payment)
    await state.set_state(SettingsStates.choosing_bc_coin)
    await callback.answer()

    data = await state.get_data()
    exchange = data.get("exchange", "bestchange_1")
    pay_label = PAYMENT_SLUGS.get(payment, payment)
    current = settings_storage.get_exchange_settings(callback.from_user.id, exchange)
    coin = data.get("coin") or current.get("coin", "tether-bep20")
    coin_label = COIN_SLUGS.get(coin, coin)
    label = EXCHANGE_LABELS.get(exchange, exchange)

    await _edit_or_send(
        callback,
        f"<b>{label} — источник данных</b>\nБанк: {pay_label}\nТекущий актив: {coin_label}\n\nВыберите актив:",
        get_settings_bc_coin_keyboard(),
    )


@router.callback_query(SettingsStates.choosing_bc_coin, F.data.startswith("bc_coin_"))
async def cb_settings_bc_coin(callback: CallbackQuery, state: FSMContext):
    """Сохраняет источник данных (банк + монета) и возвращает в bc-меню."""
    coin = callback.data.removeprefix("bc_coin_")
    await callback.answer()

    data = await state.get_data()
    exchange = data.get("exchange", "bestchange_1")
    payment = data.get("payment", "sberbank")

    # Сохраняем только источник (payment+coin); mode/value берутся из существующих настроек
    existing = settings_storage.get_exchange_settings(callback.from_user.id, exchange)
    settings_storage.set_exchange_settings(
        callback.from_user.id, exchange,
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
        + _format_bc_menu_text(callback.from_user.id, exchange),
        get_settings_bc_menu_keyboard(),
    )


@router.callback_query(SettingsStates.choosing_bybit_section, F.data.in_({"bybit_section_amount", "bybit_section_display"}))
async def cb_settings_bybit_section(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор раздела настроек Bybit: сумма сделки или выдача."""
    await callback.answer()
    data = await state.get_data()
    exchange = data.get("exchange", "bybit_1")
    current = settings_storage.get_exchange_settings(callback.from_user.id, exchange)
    label = EXCHANGE_LABELS.get(exchange, exchange)

    if callback.data == "bybit_section_amount":
        # → выбор суммы сделки
        max_amount = current.get("max_amount", 100000)
        amount_label = _format_amount_label(max_amount)
        await _edit_or_send(
            callback,
            f"<b>{label} — сумма сделки</b>\n"
            f"Текущая: <b>{amount_label}</b>\n\n"
            f"Выберите сумму вашей сделки:",
            get_settings_bybit_amount_keyboard(),
        )
    else:
        # → выбор режима выдачи
        mode = current.get("mode", "sequential")
        value = current.get("value", 10)
        current_desc = f"первые {value}" if mode == "sequential" else f"позиции {', '.join(str(v) for v in value)}"
        await state.set_state(SettingsStates.choosing_mode)
        await _edit_or_send(
            callback,
            f"<b>{label} — выдача</b>\nТекущая настройка: {current_desc}\n\nВыберите режим отображения:",
            get_settings_mode_keyboard(),
        )


@router.callback_query(SettingsStates.choosing_bybit_section, F.data == "bybit_amount_custom")
async def cb_settings_bybit_amount_custom(callback: CallbackQuery, state: FSMContext):
    """Переходит к ручному вводу суммы сделки."""
    await callback.answer()
    await state.set_state(SettingsStates.waiting_for_bybit_amount)
    data = await state.get_data()
    exchange = data.get("exchange", "bybit_1")
    current = settings_storage.get_exchange_settings(callback.from_user.id, exchange)
    current_label = _format_amount_label(current.get("max_amount", 100000))
    label = EXCHANGE_LABELS.get(exchange, exchange)
    await _edit_or_send(
        callback,
        f"<b>{label} — сумма сделки</b>\n"
        f"Текущая: <b>{current_label}</b>\n\n"
        f"Введите сумму в рублях (целое число, минимум 1000):\n"
        f"Например: <b>150000</b>",
        get_settings_input_keyboard(),
    )


@router.callback_query(SettingsStates.choosing_bybit_section, F.data.startswith("bybit_amount_"))
async def cb_settings_bybit_amount(callback: CallbackQuery, state: FSMContext):
    """Сохраняет выбранную сумму сделки и возвращает в суб-меню Bybit."""
    amount = int(callback.data.removeprefix("bybit_amount_"))
    await callback.answer()

    data = await state.get_data()
    exchange = data.get("exchange", "bybit_1")

    # Сохраняем только max_amount; mode/value берутся из существующих настроек
    existing = settings_storage.get_exchange_settings(callback.from_user.id, exchange)
    settings_storage.set_exchange_settings(
        callback.from_user.id, exchange,
        mode=existing.get("mode", "sequential"),
        value=existing.get("value", 10),
        max_amount=amount,
    )

    amount_label = _format_amount_label(amount)
    await state.set_state(SettingsStates.choosing_bybit_section)
    await _edit_or_send(
        callback,
        f"✅ Сумма сохранена: <b>{amount_label}</b>\n\n"
        + _format_bybit_menu_text(callback.from_user.id, exchange),
        get_settings_bybit_menu_keyboard(),
    )


@router.message(SettingsStates.waiting_for_bybit_amount)
async def process_bybit_amount_value(message: Message, state: FSMContext):
    """Обрабатывает ввод произвольной суммы сделки для Bybit."""
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    settings_msg_id = data.get("settings_msg_id")
    exchange = data.get("exchange", "bybit_1")

    async def show_error(err: str):
        prompt = (
            "Введите сумму в рублях (целое число, минимум 1000):\n"
            "Например: <b>150000</b>"
        )
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
            await message.answer(full, reply_markup=get_settings_input_keyboard(), parse_mode="HTML")

    text = (message.text or "").strip()
    if not text.isdecimal() or int(text) < 1:
        await show_error("❌ Введите положительное целое число (например: <b>150000</b>).")
        return
    amount = int(text)
    if amount < 1000:
        await show_error("❌ Минимальная сумма — <b>1 000 ₽</b>.")
        return
    if amount > 100_000_000:
        await show_error("❌ Максимальная сумма — <b>100 000 000 ₽</b>.")
        return

    existing = settings_storage.get_exchange_settings(message.from_user.id, exchange)
    settings_storage.set_exchange_settings(
        message.from_user.id, exchange,
        mode=existing.get("mode", "sequential"),
        value=existing.get("value", 10),
        max_amount=amount,
    )

    amount_label = _format_amount_label(amount) if amount % 1000 == 0 else f"{amount:,}".replace(",", " ")
    await state.set_state(SettingsStates.choosing_bybit_section)
    confirm_text = (
        f"✅ Сумма сохранена: <b>{amount_label} ₽</b>\n\n"
        + _format_bybit_menu_text(message.from_user.id, exchange)
    )
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=settings_msg_id,
            text=confirm_text,
            reply_markup=get_settings_bybit_menu_keyboard(),
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(confirm_text, reply_markup=get_settings_bybit_menu_keyboard(), parse_mode="HTML")


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
    exchange = data.get("exchange", "bybit_1")
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
        if not text.isdecimal() or int(text) < 1:
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
        if not all(p.isdecimal() and int(p) >= 1 for p in parts):
            await show_error("❌ Все номера должны быть положительными числами.\nПример: <b>1, 3, 5, 7</b>")
            return
        value = sorted(set(int(p) for p in parts))
        if any(v > 100 for v in value):
            await show_error("❌ Номер позиции не может быть больше 100.")
            return
        settings_storage.set_exchange_settings(message.from_user.id, exchange, mode, value,
                                               payment=payment, coin=coin)
        desc = f"позиции {', '.join(str(v) for v in value)}"

    # После сохранения: BestChange → bc-меню, Bybit → bybit-меню
    if _is_bc(exchange):
        await state.set_state(SettingsStates.choosing_bc_section)
        confirm_text = f"✅ Выдача сохранена: <b>{desc}</b>\n\n" + _format_bc_menu_text(message.from_user.id, exchange)
        reply_markup = get_settings_bc_menu_keyboard()
    elif _is_bybit(exchange):
        await state.set_state(SettingsStates.choosing_bybit_section)
        confirm_text = f"✅ Выдача сохранена: <b>{desc}</b>\n\n" + _format_bybit_menu_text(message.from_user.id, exchange)
        reply_markup = get_settings_bybit_menu_keyboard()

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
