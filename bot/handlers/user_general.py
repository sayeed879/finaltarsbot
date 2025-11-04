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

# ... (rest of the file content
# --- Handler for the /help command ---
# This also handles the "🆘 /help" button click
@router.message(Command(commands=["help"]))
@router.message(F.text == "🆘 /help")
async def handle_help(message: Message, db_pool):
    await user_queries.update_user_last_active(db_pool, message.from_user.id)
    
    help_text = (
        "<b>Here are the commands you can use:</b>\n\n"
        "<b>/start</b> - Start or restart the bot\n"
        "<b>/stop</b> - Cancel any current operation\n"
        "<b>/changeclass</b> - Change your selected class\n"
        "<b>/stats</b> - Check your account status and limits\n"
        "<b>/help</b> - Show this help message\n\n"
        "You can also use the buttons on the main menu to access features."
    )
    await message.answer(help_text, reply_markup=get_main_menu_keyboard())

# --- Handler for the user's /stats command ---
@router.message(Command(commands=["stats"]))
async def handle_stats(message: Message, db_pool):
    user_id = message.from_user.id
    await user_queries.update_user_last_active(db_pool, user_id)
    
    user = await user_queries.get_user(db_pool, user_id)
    
    if not user:
        await message.answer("Please type /start to register first.")
        return

    # Format the stats message
    if user.is_premium:
        status = "💎 Premium User"
        expiry_date = user.premium_expiry_date.strftime("%Y-%m-%d at %H:%M")
        plan_info = f"<b>Plan Expires:</b> {expiry_date}\n"
    else:
        status = "👤 Free User"
        plan_info = "<b>Plan:</b> Use /upgrade to get premium!\n"

    stats_text = (
        f"<b>Your Account Stats:</b>\n\n"
        f"<b>Status:</b> {status}\n"
        f"<b>Class:</b> {user.selected_class}\n"
        f"{plan_info}\n"
        f"<b>Daily Limits (Resets at 00:00):</b>\n"
        f"<b>AI Queries:</b> {user.ai_limit_remaining} remaining\n"
        f"<b>PDF Downloads:</b> {user.pdf_downloads_remaining} remaining\n"
    )
    
    await message.answer(stats_text)
    # (Add this code to the end of bot/handlers/user_general.py)

# A list of keywords that will trigger the "about" response
ABOUT_TRIGGERS = [
    "who are you", 
    "who made you", 
    "developer", 
    "about you", 
    "about the bot",
    "sayeed"
]

@router.message(F.text)
async def handle_general_text(message: Message, db_pool): # Renamed function
    """
    This handler catches all text messages that aren't
    commands or specific buttons.
    """
    if not message.text:
        return

    msg_text = message.text.lower()
    await user_queries.update_user_last_active(db_pool, message.from_user.id)
    
    # Check if any trigger word is in the user's message
    if any(trigger in msg_text for trigger in ABOUT_TRIGGERS):
        response_text = (
            "I was developed by **Sayeed**.\n\n"
            "He is a 17-year-old full-stack developer!"
        )
        await message.answer(response_text)
    
    else:
        # If it's not an "about" message, it's unknown.
        await message.answer(
            "I'm not sure what you mean. Please use the buttons "
            "or type /help to see available commands."
        )