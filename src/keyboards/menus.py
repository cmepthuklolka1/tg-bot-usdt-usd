from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Returns the main menu keyboard."""
    buttons = [
        [InlineKeyboardButton(text="📊 Курс USD/USDT", callback_data="show_rates")]
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
