# In bot/handlers/unknown_text.py

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import StateFilter
from bot.keyboards.reply import get_main_menu_keyboard
from bot.db import user_queries # <-- ADD THIS IMPORT

router = Router()

ABOUT_TRIGGERS = [
    "who are you", 
    "who made you", 
    "developer", 
    "about you", 
    "about the bot",
    "sayeed",
    "who created",
    "creator"
]

@router.message(StateFilter(None), F.text)
async def handle_unknown_text(message: Message, db_pool): # <-- ADD db_pool
    """
    Catch-all handler for any text that doesn't match other commands or handlers.
    Runs only when no other handler matches.
    """
    if not message.text:
        return

    msg_text = message.text.lower().strip()
    await user_queries.update_user_last_active(db_pool, message.from_user.id)
    
    # Check if any trigger word is in the user's message
    if any(trigger in msg_text for trigger in ABOUT_TRIGGERS):
        response_text = (
            "<b>ℹ️ About This Bot</b>\n\n"
            "<b>Developer:</b> Sayeed\n"
            "<b>Age:</b> 17 years old\n"
            "<b>Skills:</b> Full-stack developer\n\n"
            "<b>Bot Features:</b>\n"
            "• 🤖 AI-powered chat assistant\n"
            "• 📚 PDF search and download system\n"
            "• 💎 Premium subscription system\n"
            "• 🔐 Secure payment verification\n"
            "• 📊 Advanced analytics and stats\n\n"
            "<b>Technology Stack:</b>\n"
            "• Python 3.11 with Aiogram 3\n"
            "• PostgreSQL database\n"
            "• Redis caching\n"
            "• Google Gemini AI integration\n"
            "• AIOHTTP webhook server\n\n"
            "Use /help to see all available commands!"
        )
        await message.answer(response_text)
        return # <-- ADD RETURN
    
    # Greetings
    elif any(word in msg_text for word in ["hello", "hi", "hey", "namaste"]):
        first_name = message.from_user.first_name or "there"
        await message.answer(
            f"👋 Hello {first_name}!\n\n"
            "I'm your educational assistant bot. Here's what I can do:\n\n"
            "• 🔎 Search and download PDFs\n"
            "• 💬 Chat with AI\n"
            "• 💎 Premium features\n\n"
            "Use the buttons below or type /help for more information!",
            reply_markup=get_main_menu_keyboard()
        )
        return # <-- ADD RETURN
    
    # Thanks
    elif any(word in msg_text for word in ["thanks", "thank you", "thx"]):
        await message.answer(
            "You're welcome! 😊\n\n"
            "Happy to help. Let me know if you need anything else!\n\n"
            "Use /help if you have questions."
        )
        return # <-- ADD RETURN
    
    # If no logic matched, THEN send the unknown message
    await message.answer(
        "🤔 <b>Not Sure What You Mean</b>\n\n"
        "I didn't understand that message. Here's what you can do:\n\n"
        "• Use the <b>buttons below</b> for quick access\n"
        "• Type /help to see all commands\n"
        "• Type /start to restart the bot\n"
        "• Click <b>💬 Chat with AI</b> to ask questions\n\n"
        "<i>Tip: Use the menu buttons for easier navigation!</i>",
        reply_markup=get_main_menu_keyboard()
    )