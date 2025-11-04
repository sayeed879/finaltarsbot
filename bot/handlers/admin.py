import logging
from aiogram import Router, F, Bot
# --- THIS IS THE FIX ---
# We import CallbackQuery from aiogram.types, not 'telegram'
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from typing import Optional, Tuple

# Our component imports
from bot.config import ADMIN_ID
from bot.fsm.states import AdminFlow
from bot.db import user_queries, pdf_queries
from bot.keyboards import inline as inline_keyboards

# --- Admin-Only Filter ---
class AdminFilter(Filter):
    async def __call__(self, event) -> bool:
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return False
        return user_id == ADMIN_ID

router = Router()
# Apply filter to both messages and callback queries
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

# --- Helper Function for Parsing Commands ---
def parse_command(text: str) -> Tuple[str, Optional[str]]:
    """
    Parses a command like '/cmd 123' or '/cmd <message>'.
    Returns (command, argument)
    """
    if ' ' not in text:
        return (text, None)
    
    command, argument = text.split(' ', 1)
    return (command, argument.strip())

# --- Admin: User Management ---

@router.message(Command(commands=["upgradeuser"]))
async def admin_upgrade_user(message: Message, bot: Bot, db_pool):
    command, arg = parse_command(message.text)
    
    if not arg or not arg.isdigit():
        await message.answer("Usage: `/upgradeuser <user_id>`")
        return

    user_id = int(arg)
    
    success = await user_queries.upgrade_user_to_premium(db_pool, user_id)
    if success:
        await message.answer(f"✅ User `{user_id}` has been upgraded to premium.")
        try:
            await bot.send_message(
                user_id,
                "🎉 **Congratulations!** Your plan has been approved.\n"
                "You are now a 💎 Premium User for the next 30 days!"
            )
        except Exception as e:
            await message.answer(f"Could not notify user (they may have blocked the bot): {e}")
    else:
        await message.answer(f"❌ Failed to upgrade user `{user_id}`.")

@router.message(Command(commands=["endplan"]))
async def admin_end_plan(message: Message, bot: Bot, db_pool):
    command, arg = parse_command(message.text)
    if not arg or not arg.isdigit():
        await message.answer("Usage: `/endplan <user_id>`")
        return

    user_id = int(arg)
    success = await user_queries.end_user_plan(db_pool, user_id)
    if success:
        await message.answer(f"✅ Premium plan ended for user `{user_id}`.")
    else:
        await message.answer(f"❌ Failed to end plan for user `{user_id}`.")

@router.message(Command(commands=["extendlimit"]))
async def admin_extend_limit(message: Message, db_pool):
    command, arg_string = parse_command(message.text)
    
    if not arg_string:
        await message.answer("Usage: `/extendlimit <user_id> <days>`")
        return
        
    try:
        user_id_str, days_str = arg_string.split(' ', 1)
        user_id = int(user_id_str)
        days = int(days_str)
    except ValueError:
        await message.answer("Usage: `/extendlimit <user_id> <days>`\nBoth must be numbers.")
        return

    success = await user_queries.extend_user_premium(db_pool, user_id, days)
    if success:
        await message.answer(f"✅ Extended premium for user `{user_id}` by `{days}` days.")
    else:
        await message.answer(f"❌ Failed to extend plan. Is the user premium?")

# --- Admin: Stats ---

@router.message(Command(commands=["stats"]))
async def admin_stats(message: Message, db_pool):
    stats = await user_queries.get_bot_stats(db_pool)
    
    stats_text = (
        f"<b>📊 Bot Statistics</b>\n\n"
        f"<b>Total Users:</b> {stats.total_users}\n"
        f"<b>Total Premium:</b> {stats.total_premium}\n"
        f"<b>Active Today:</b> {stats.active_today}"
    )
    await message.answer(stats_text)

# --- Admin: Delete PDF ---

@router.message(Command(commands=["deletepdf"]))
async def admin_delete_pdf(message: Message, db_pool):
    command, query = parse_command(message.text)
    
    if not query:
        await message.answer("Usage: `/deletepdf <search term>`\n\nI will search for PDFs with that term in their title.")
        return

    pdf_results = await pdf_queries.admin_search_pdfs_by_title(db_pool, query)
    
    if not pdf_results:
        await message.answer(f"I couldn't find any PDFs with the title '<b>{query}</b>'.")
        return
        
    if len(pdf_results) > 20:
        await message.answer("Found over 20 matches. Please be more specific.")
        return

    await message.answer(
        f"Found <b>{len(pdf_results)}</b> match(es) for '<b>{query}</b>'.\n"
        "Which one do you want to delete?",
        reply_markup=inline_keyboards.get_pdf_deletion_keyboard(pdf_results)
    )

@router.callback_query(F.data.startswith("del_select:"))
async def admin_select_pdf_to_delete(callback: CallbackQuery, state: FSMContext):
    pdf_id = int(callback.data.split(":")[1])
    
    pdf_title = ""
    for button in callback.message.reply_markup.inline_keyboard:
        if button[0].callback_data == callback.data:
            pdf_title = button[0].text
            break
    
    await state.set_state(AdminFlow.DeletePDF_AwaitingConfirmation)
    await state.update_data(pdf_id=pdf_id, pdf_title=pdf_title)
    
    await callback.message.edit_text(
        f"Are you sure you want to permanently delete this file?\n\n"
        f"<b>{pdf_title}</b>\n\n"
        "This action cannot be undone.",
        reply_markup=inline_keyboards.get_delete_confirmation_keyboard(pdf_id)
    )
    await callback.answer()

@router.callback_query(AdminFlow.DeletePDF_AwaitingConfirmation, F.data.startswith("del_confirm:"))
async def admin_confirm_delete(callback: CallbackQuery, state: FSMContext, db_pool):
    pdf_id = int(callback.data.split(":")[1])
    
    data = await state.get_data()
    pdf_title = data.get('pdf_title', f"ID: {pdf_id}")
    
    success = await pdf_queries.delete_pdf_by_id(db_pool, pdf_id)
    
    if success:
        await callback.message.edit_text(f"✅ Successfully deleted:\n<b>{pdf_title}</b>")
    else:
        await callback.message.edit_text(f"❌ Error: Could not delete <b>{pdf_title}</b>.")
        
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "del_cancel")
async def admin_cancel_delete(callback: CallbackQuery, state: FSMContext):
    if await state.get_state() is not None:
        await state.clear()
        
    await callback.message.edit_text("❌ Deletion cancelled.")
    await callback.answer()

# --- Admin: Broadcast ---

@router.message(Command(commands=["broadcast"]))
async def admin_broadcast(message: Message, state: FSMContext):
    command, arg = parse_command(message.text)
    
    if not arg:
        await state.set_state(AdminFlow.AwaitingBroadcastMessage)
        await message.answer(
            "OK, send me the message you want to broadcast. "
            "It can be text, photo, or a document.\n\nType /stop to cancel."
        )
    else:
        await message.answer("Broadcasting with a message like `/broadcast Hello` is not set up yet. Use just `/broadcast`.")

@router.message(AdminFlow.AwaitingBroadcastMessage)
async def broadcast_message_received(message: Message, state: FSMContext, db_pool):
    await state.clear()
    await message.answer("Broadcast message received. (Logic to send to all users is not yet built).")
    logging.info("Broadcast message captured but not sent.")