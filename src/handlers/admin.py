import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from ..config import config
from ..keyboards.menus import get_admin_menu_keyboard, get_main_menu_keyboard
from ..utils.storage import WhitelistStorage, BannedSellersStorage

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()
logger = logging.getLogger(__name__)
storage = WhitelistStorage()
banned_storage = BannedSellersStorage()

# Текст приглашения, которое получит пользователь при выдаче доступа
INVITE_TEXT = (
    "🎉 <b>Вам предоставлен доступ!</b>\n\n"
    "Теперь вы можете пользоваться ботом для мониторинга курсов USD/USDT.\n"
    "Нажмите /start чтобы открыть меню."
)

class AdminStates(StatesGroup):
    waiting_for_add_user = State()
    waiting_for_remove_user = State()
    waiting_for_ban_seller = State()
    waiting_for_unban_seller = State()

@router.message(Command("cancel"))
@router.message(F.text.casefold() == "отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_menu_keyboard(is_admin=True))

@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.admin_id:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
        
    await state.clear()
    
    text = (
        "<b>👮 Управление пользователями</b>\n\n"
        "Выдать доступ:\n"
        "<code>/add_user</code>\n\n"
        "Забрать доступ:\n"
        "<code>/remove_user</code>\n\n"
        "<b>⛔ Чёрный список Bybit</b>\n\n"
        "Забанить продавца (скрыть из выдачи):\n"
        "<code>/ban_seller</code>\n\n"
        "Разбанить продавца:\n"
        "<code>/unban_seller</code>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_menu_keyboard(), parse_mode="HTML")

#
# 1. Добавление пользователя
#
@router.message(Command("add_user"))
async def cmd_add_user(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        return
    
    await message.answer("Введите ID пользователя, которому нужно выдать доступ:")
    await state.set_state(AdminStates.waiting_for_add_user)

@router.message(AdminStates.waiting_for_add_user)
async def process_add_user(message: Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуйте ещё раз.")
        return
        
    target_id = int(message.text)
    if storage.add_user(target_id):
        await message.answer(f"✅ Пользователь {target_id} успешно добавлен в белый список.")

        try:
            await bot.send_message(
                chat_id=target_id,
                text=INVITE_TEXT,
                parse_mode="HTML",
                reply_markup=get_main_menu_keyboard(is_admin=False)
            )
            await message.answer("📨 Пользователь уведомлён об открытии доступа.")
        except Exception as e:
            logger.warning(f"Не удалось отправить приглашение пользователю {target_id}: {e}")
            await message.answer(
                "⚠️ Пользователь добавлен, но уведомить его не удалось.\n"
                "Возможно, он ещё ни разу не запускал бота — пусть сделает <b>/start</b>.",
                parse_mode="HTML"
            )
            
        from ..utils.commands import set_bot_commands
        await set_bot_commands(bot)
    else:
        await message.answer(f"ℹ️ Пользователь {target_id} уже есть в белом списке.")
        
    await state.clear()

#
# 2. Удаление пользователя
#
@router.message(Command("remove_user"))
async def cmd_remove_user(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        return
    
    users = storage._read_data().get("users", [])
    if not users:
        await message.answer("Список пользователей пуст.")
        return
        
    users_text = "\n".join([f"<code>{u}</code>" for u in users])
    await message.answer(
        f"<b>Текущие пользователи:</b>\n{users_text}\n\n"
        "Введите ID пользователя для удаления (тапните по ID выше для копирования):",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_remove_user)

@router.message(AdminStates.waiting_for_remove_user)
async def process_remove_user(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуйте ещё раз.")
        return
        
    target_id = int(message.text)
    if target_id == config.admin_id:
        await message.answer("❌ Вы не можете удалить самого себя (Администратора) из белого списка.")
        await state.clear()
        return
        
    if storage.remove_user(target_id):
        await message.answer(f"✅ Пользователь {target_id} удален из белого списка.")
        from ..utils.commands import set_bot_commands
        await set_bot_commands(message.bot)
    else:
        await message.answer(f"ℹ️ Пользователя {target_id} нет в белом списке.")
        
    await state.clear()


#
# 3. Баним продавца
#
@router.message(Command("ban_seller"))
async def cmd_ban_seller(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        return
    
    await message.answer("Введите имя продавца Bybit для добавления в чёрный список:")
    await state.set_state(AdminStates.waiting_for_ban_seller)

@router.message(AdminStates.waiting_for_ban_seller)
async def process_ban_seller(message: Message, state: FSMContext):
    seller_name = message.text.strip()
    if banned_storage.ban_seller(seller_name):
        await message.answer(f"✅ Продавец <b>{seller_name}</b> добавлен в чёрный список.", parse_mode="HTML")
    else:
        await message.answer(f"ℹ️ Продавец <b>{seller_name}</b> уже есть в чёрном списке.", parse_mode="HTML")
        
    await state.clear()


#
# 4. Разбаниваем продавца
#
@router.message(Command("unban_seller"))
async def cmd_unban_seller(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        return
        
    banned = banned_storage.get_banned()
    if not banned:
        await message.answer("Чёрный список продавцов пуст.")
        return
        
    banned_text = "\n".join([f"<code>{s}</code>" for s in banned])
    await message.answer(
        f"<b>Забаненные продавцы:</b>\n{banned_text}\n\n"
        "Введите имя продавца для удаления из ЧС (тапните по имени для копирования):",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_unban_seller)

@router.message(AdminStates.waiting_for_unban_seller)
async def process_unban_seller(message: Message, state: FSMContext):
    seller_name = message.text.strip()
    if banned_storage.unban_seller(seller_name):
        await message.answer(f"✅ Продавец <b>{seller_name}</b> удалён из чёрного списка.", parse_mode="HTML")
    else:
        await message.answer(f"ℹ️ Продавца <b>{seller_name}</b> нет в чёрном списке.", parse_mode="HTML")
        
    await state.clear()
