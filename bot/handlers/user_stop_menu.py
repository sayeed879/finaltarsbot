"""
STOP, MENU, HELP, and STATS Handlers

CRITICAL: These handlers MUST be registered FIRST in __init__.py
They need to work from ANY state, including FSM states.

DO NOT add StateFilter to /stop - it must work everywhere!
"""

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

# Our component imports
from bot.keyboards.reply import get_main_menu_keyboard
from bot.db import user_queries
from bot.fsm.states import UserFlow, AdminFlow

# Initialize router with HIGH PRIORITY
router = Router()

# =============================================================================
# /STOP HANDLER - HIGHEST PRIORITY - NO STATE FILTER
# =============================================================================

@router.message(Command("stop"))
async def handle_stop_command(message: Message, state: FSMContext, db_pool):
    """
    Cancel ANY active operation and return to main menu.
    This handler has NO state filter, so it works from ANY state.
    
    CRITICAL: This MUST be registered first in __init__.py
    """
    user_id = message.from_user.id

    # Update last active time
    try:
        await user_queries.update_user_last_active(db_pool, user_id)
    except Exception as e:
        logging.warning(f"Could not update last_active: {e}")

    # Get the current FSM state
    current_state = await state.get_state()

    if current_state:
        # Clear FSM
        await state.clear()

        # Detect which process was cancelled
        state_messages = {
            UserFlow.AwaitingClassSelection: "Class selection",
            UserFlow.AwaitingSearchQuery: "PDF search",
            UserFlow.AwaitingAIPrompt: "AI chat",
            UserFlow.AwaitingScreenshot: "Payment process",
            AdminFlow.AwaitingBroadcastMessage: "Broadcast message",
            AdminFlow.AddPDF_AwaitingTitle: "PDF upload",
            AdminFlow.DeletePDF_AwaitingConfirmation: "PDF deletion"
        }

        operation = "operation"
        for st, msg in state_messages.items():
            if current_state == st.state:
                operation = msg
                break

        await message.answer(
            f"🛑 <b>{operation.title()} Cancelled</b>\n\n"
            "You are now back in the main menu.\n\n"
            "Use the buttons below or type /help for assistance.",
            reply_markup=get_main_menu_keyboard()
        )
        
        logging.info(f"User {user_id} cancelled operation: {operation}")

    else:
        await message.answer(
            "ℹ️ <b>No Active Operation</b>\n\n"
            "You weren't in any active process.\n\n"
            "Here's the main menu:",
            reply_markup=get_main_menu_keyboard()
        )

# =============================================================================
# /MENU HANDLER - Show main menu (only when not in FSM state)
# =============================================================================