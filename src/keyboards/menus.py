from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Returns the main menu keyboard."""
    buttons = [
        [InlineKeyboardButton(text="📊 Курс USD/USDT", callback_data="show_rates")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings_menu")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_rates_keyboard() -> InlineKeyboardMarkup:
    """Keyboard under the exchange rates message."""
    buttons = [
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_rates")],
        [
            InlineKeyboardButton(text="⚙️ BestChange", callback_data="settings_bestchange"),
            InlineKeyboardButton(text="⚙️ Bybit P2P",  callback_data="settings_bybit"),
        ],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for admin user settings menu."""
    buttons = [
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_exchange_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing which exchange to configure."""
    buttons = [
        [InlineKeyboardButton(text="📈 BestChange", callback_data="settings_bestchange")],
        [InlineKeyboardButton(text="💰 Bybit P2P", callback_data="settings_bybit")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_mode_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing display mode (sequential or by positions)."""
    buttons = [
        [InlineKeyboardButton(text="📋 Подряд (первые N)", callback_data="mode_sequential")],
        [InlineKeyboardButton(text="🔢 По номерам (1,3,5,...)", callback_data="mode_positions")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_input_keyboard() -> InlineKeyboardMarkup:
    """Minimal keyboard shown while waiting for text input in settings."""
    buttons = [
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="settings_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_bc_menu_keyboard() -> InlineKeyboardMarkup:
    """BestChange sub-menu: choose what to configure."""
    buttons = [
        [InlineKeyboardButton(text="🏦 Источник данных", callback_data="bc_section_source")],
        [InlineKeyboardButton(text="📋 Настройки выдачи", callback_data="bc_section_display")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_bc_payment_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing BestChange payment method (bank)."""
    buttons = [
        [InlineKeyboardButton(text="Сбербанк",   callback_data="bc_pay_sberbank")],
        [InlineKeyboardButton(text="Альфа-Банк", callback_data="bc_pay_alfaclick")],
        [InlineKeyboardButton(text="Т-Банк",     callback_data="bc_pay_tinkoff")],
        [InlineKeyboardButton(text="ВТБ",         callback_data="bc_pay_vtb")],
        [InlineKeyboardButton(text="◀️ Назад",   callback_data="settings_bestchange")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_bc_coin_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing BestChange coin (USDT network)."""
    buttons = [
        [InlineKeyboardButton(text="USDT ERC20", callback_data="bc_coin_tether-erc20")],
        [InlineKeyboardButton(text="USDT TRC20", callback_data="bc_coin_tether-trc20")],
        [InlineKeyboardButton(text="USDT BEP20", callback_data="bc_coin_tether-bep20")],
        [InlineKeyboardButton(text="USDT TON",   callback_data="bc_coin_tether-ton")],
        [InlineKeyboardButton(text="◀️ Назад",   callback_data="settings_bestchange")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
