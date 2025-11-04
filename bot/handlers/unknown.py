import logging
from mailbox import Message
import re
from aiogram import Router
from keyboards import get_main_menu_keyboard

router = Router()

@router.message()
async def handle_unknown_message(message: Message):
    if not message.text:
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