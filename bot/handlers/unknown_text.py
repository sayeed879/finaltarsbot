from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import StateFilter
from bot.keyboards.reply import get_main_menu_keyboard

router = Router()

@router.message(StateFilter(None), F.text)
async def handle_unknown_text(message: Message):
    """
    Catch-all handler for any text that doesn't match other commands or handlers.
    Runs only when no other handler matches.
    """
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
