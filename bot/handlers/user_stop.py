import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

# Our component imports
from bot.keyboards.reply import get_main_menu_keyboard
from bot.db import user_queries

# Assuming 'router' is defined here or imported
router = Router() 
# ... (rest of your imports) ...

# --- Handler for the /stop command ---
@router.message(Command(commands=["stop"]))
async def handle_stop(message: Message, fsm_context: FSMContext, db_pool):
    user_id = message.from_user.id
    
    # Update last active time (Good practice)
    await user_queries.update_user_last_active(db_pool, user_id)
    
    # 1. Get the current state
    current_state = await fsm_context.get_state()
    
    # 2. Check if the user is in ANY state
    if current_state:
        # 3. Clear the state: This is the core action
        await fsm_context.clear()
        
        # 4. Acknowledge and present the main menu
        await message.answer(
            "🛑 **Action Cancelled.** You are now back in the main menu.",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        # If not in a state, just send a confirmation (Good fallback)
        await message.answer(
            "You weren't in any active operation. Here is the main menu.",
            reply_markup=get_main_menu_keyboard()
        )

# ... (rest of the file content) ...