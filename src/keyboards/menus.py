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
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main")]
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
