from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Creates the main menu reply keyboard with ALL essential buttons.
    FIXED VERSION: Now includes menu button
    """
    builder = ReplyKeyboardBuilder()

    # Row 1: Main features
    builder.row(
        KeyboardButton(text="💬 Chat with Ai"),
        KeyboardButton(text="🔎 Search for pdf")
    )
    
    # Row 2: Premium and Menu
    builder.row(
        KeyboardButton(text="💎 Access premium content"),
        KeyboardButton(text="🏠 Main Menu")
    )
    
    # Row 3: Help
    builder.row(
        KeyboardButton(text="🆘 /help")
    )

    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Choose an option or type /stop..."
    )

def get_minimal_keyboard() -> ReplyKeyboardMarkup:
    """
    Creates a minimal keyboard for specific situations (e.g., during onboarding).
    """
    builder = ReplyKeyboardBuilder()
    
    builder.row(
        KeyboardButton(text="🆘 /help"),
        KeyboardButton(text="🏠 Main Menu")
    )
    
    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Type a command or use buttons..."
    )