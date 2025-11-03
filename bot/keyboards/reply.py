from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Creates the main menu reply keyboard.
    """
    # ReplyKeyboardBuilder is the modern way to build these
    builder = ReplyKeyboardBuilder()

    # Add buttons. 'resize_keyboard=True' makes it fit the screen.
    # 'input_field_placeholder' is the grey text in the message box.
    builder.row(
        KeyboardButton(text="💬 Chat with Ai"),
        KeyboardButton(text="🔎 Search for pdf")
    )
    builder.row(
        KeyboardButton(text="💎 Access premium content"),
        KeyboardButton(text="🆘 /help")
    )

    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Choose an option or type /stop..."
    )