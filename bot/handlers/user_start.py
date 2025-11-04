import logging
from typing import Any

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

# Router for this module
router = Router()


async def is_user_in_channel(bot: Bot, user_id: int) -> bool:
    """
    Checks if a user is a member of the specified channel.
    """
    try:
        chat_member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if chat_member.status not in ["left", "kicked"]:
            return True
    except TelegramBadRequest:
        # User not in channel or invalid id
        return False
    except Exception as e:
        logging.error(f"Error checking channel membership for {user_id}: {e}")
        return False
    return False


# --- Shared business logic: start / onboarding flow ---
async def start_user_flow(message: Message, bot: Bot, state: FSMContext, db_pool: Any):
    """
    Shared logic to register/check user and route them to class selection
    or main menu. This is a pure function (not a router handler) and can be
    safely called from multiple handlers while preserving DI.
    """
    if message is None:
        logging.warning("start_user_flow called with message=None")
        return

    user_id = message.from_user.id
    username = message.from_user.username

    # 1. Update user's last_active timestamp (fire-and-forget or awaited based on your preference)
    try:
        await user_queries.update_user_last_active(db_pool, user_id)
    except Exception as e:
        logging.exception(f"Failed to update last_active for {user_id}: {e}")

    # 2. Check channel membership
    if not await is_user_in_channel(bot, user_id):
        await message.answer(
            "Welcome! To use this bot, you must first join our channel.",
            reply_markup=get_channel_join_keyboard(CHANNEL_ID),
        )
        return

    # 3. Ensure user exists in DB
    try:
        user = await user_queries.get_user(db_pool, user_id)
        if not user:
            user = await user_queries.create_user(db_pool, user_id, username)
    except Exception as e:
        logging.exception(f"DB error while getting/creating user {user_id}: {e}")
        await message.answer("Sorry, an internal error occurred. Please try again later.")
        return

    # 4. If no class selected -> put into FSM class selection
    if getattr(user, "selected_class", "none") == "none":
        await state.set_state(UserFlow.AwaitingClassSelection)
        await message.answer(
            "Welcome! I see you're all set. Please select your class to continue:",
            reply_markup=get_class_selection_keyboard(),
        )
        return

    # 5. User fully set up -> send main menu
    first_name = message.from_user.first_name or "there"
    await message.answer(
        f"Welcome back, {first_name}!\n"
        f"You are in class: <b>{user.selected_class}</b>. (Use /changeclass to modify)",
        reply_markup=get_main_menu_keyboard(),
    )


# --- Handler for the /start command ---
@router.message(CommandStart())
async def handle_start(message: Message, bot: Bot, state: FSMContext, db_pool: Any):
    await start_user_flow(message, bot, state, db_pool)


# --- Handler for the "✅ Joined" button ---
@router.callback_query(F.data == "check_join")
async def handle_check_join(callback: CallbackQuery, bot: Bot, state: FSMContext, db_pool: Any):
    # Answer callback to stop the spinner
    await callback.answer("Checking your membership status...")

    # callback.message should exist for inline keyboard callbacks; guard just in case
    if not callback.message:
        logging.warning("handle_check_join: callback.message is None")
        await callback.answer("Couldn't verify join status. Try /start.")
        return

    # Re-run the shared start flow (preserves DI)
    await start_user_flow(callback.message, bot, state, db_pool)

    # Delete the join prompt message (if you want)
    try:
        await callback.message.delete()
    except Exception:
        # Non-fatal: log and continue
        logging.debug("Could not delete join message (maybe already removed).")


# --- Handler for the /changeclass command ---
@router.message(Command(commands=["changeclass"]))
async def handle_change_class(message: Message, state: FSMContext, db_pool: Any):
    # Update last active
    try:
        await user_queries.update_user_last_active(db_pool, message.from_user.id)
    except Exception:
        logging.debug("Failed to update last active on changeclass")

    await state.set_state(UserFlow.AwaitingClassSelection)
    await message.answer(
        "Please select your new class:",
        reply_markup=get_class_selection_keyboard(),
    )


# --- Handler for the Class Selection Buttons ---
@router.callback_query(UserFlow.AwaitingClassSelection, F.data.startswith("class:"))
async def handle_class_selection(callback: CallbackQuery, state: FSMContext, db_pool: Any):
    # Get the class from the button data (e.g., "class:10th" -> "10th")
    selected_class = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    # Update the user's class in the database
    success = False
    try:
        success = await user_queries.set_user_class(db_pool, user_id, selected_class)
    except Exception as e:
        logging.exception(f"Failed to set class for {user_id}: {e}")

    if success:
        # Clear the state
        await state.clear()

        # Edit the original message (to remove the buttons)
        try:
            await callback.message.edit_text(f"✅ Your class has been set to: <b>{selected_class}</b>")
        except Exception:
            logging.debug("Could not edit original class selection message.")

        # Send the main menu
        await callback.message.answer(
            "You are all set! Here is the main menu:",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await callback.message.answer("Sorry, something went wrong. Please try again.")

    # Answer the callback to stop the loading icon
    await callback.answer()
