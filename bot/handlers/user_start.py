import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

# Our component imports
from bot.config import CHANNEL_ID
from bot.fsm.states import UserFlow
from bot.keyboards.inline import get_class_selection_keyboard, get_channel_join_keyboard
from bot.keyboards.reply import get_main_menu_keyboard
from bot.db import user_queries

# We create a 'Router' for this file.
# All our handlers will be attached to this router.
router = Router()

# A helper function to check channel membership
async def is_user_in_channel(bot: Bot, user_id: int) -> bool:
    """
    Checks if a user is a member of the specified channel.
    """
    try:
        # Get member status
        chat_member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Check if they are a member/creator/admin and not left/kicked
        if chat_member.status not in ["left", "kicked"]:
            return True
    except TelegramBadRequest:
        # This happens if the user_id is not in the channel (or invalid ID)
        return False
    except Exception as e:
        # Log other potential errors
        logging.error(f"Error checking channel membership for {user_id}: {e}")
        return False
    return False

# --- Handler for the /start command ---
@router.message(CommandStart())
async def handle_start(message: Message, bot: Bot, fsm_context: FSMContext, db_pool):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # 1. Update user's last_active timestamp (fire-and-forget)
    await user_queries.update_user_last_active(db_pool, user_id)

    # 2. Check if user is in the channel
    if not await is_user_in_channel(bot, user_id):
        await message.answer(
            "Welcome! To use this bot, you must first join our channel.",
            reply_markup=get_channel_join_keyboard(CHANNEL_ID)
        )
        return

    # 3. User is in the channel. Check if they are in the database.
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        # If not in DB, create them
        user = await user_queries.create_user(db_pool, user_id, username)

    # 4. Check if they have selected a class
    if user.selected_class == 'none':
        # If no class, start the selection flow
        await fsm_context.set_state(UserFlow.AwaitingClassSelection)
        await message.answer(
            "Welcome! I see you're all set. Please select your class to continue:",
            reply_markup=get_class_selection_keyboard()
        )
    else:
        # 5. User is fully set up. Send the main menu.
        await message.answer(
            f"Welcome back, {message.from_user.first_name}!\n"
            f"You are in class: <b>{user.selected_class}</b>. (Use /changeclass to modify)",
            reply_markup=get_main_menu_keyboard()
        )

# --- Handler for the "✅ Joined" button ---
@router.callback_query(F.data == "check_join")
async def handle_check_join(callback: CallbackQuery, bot: Bot, fsm_context: FSMContext, db_pool):
    # This just re-runs the /start logic
    # We answer the callback to stop the loading icon
    await callback.answer("Checking your membership status...")
    # Trigger the /start command's logic
    await handle_start(callback.message, bot, fsm_context, db_pool)
    # We must delete the "Join" message, otherwise it's confusing
    await callback.message.delete()

# --- Handler for the /changeclass command ---
@router.message(Command(commands=["changeclass"]))
async def handle_change_class(message: Message, fsm_context: FSMContext, db_pool):
    # This handler simply puts the user into the class selection state
    await user_queries.update_user_last_active(db_pool, message.from_user.id)
    
    await fsm_context.set_state(UserFlow.AwaitingClassSelection)
    await message.answer(
        "Please select your new class:",
        reply_markup=get_class_selection_keyboard()
    )

# --- Handler for the Class Selection Buttons ---
# This catches any callback data that starts with "class:"
@router.callback_query(UserFlow.AwaitingClassSelection, F.data.startswith("class:"))
async def handle_class_selection(callback: CallbackQuery, fsm_context: FSMContext, db_pool):
    # Get the class from the button data (e.g., "class:10th" -> "10th")
    selected_class = callback.data.split(":")[1]
    user_id = callback.from_user.id

    # Update the user's class in the database
    success = await user_queries.set_user_class(db_pool, user_id, selected_class)
    
    if success:
        # Clear the state
        await fsm_context.clear()
        
        # 1. Edit the original message (to remove the buttons)
        await callback.message.edit_text(
            f"✅ Your class has been set to: <b>{selected_class}</b>"
        )
        # 2. Send the main menu
        await callback.message.answer(
            "You are all set! Here is the main menu:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await callback.message.answer(
            "Sorry, something went wrong. Please try again."
        )
    
    # Answer the callback to stop the loading icon
    await callback.answer()