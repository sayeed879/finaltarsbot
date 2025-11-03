from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Tuple # Make sure to add this

def get_class_selection_keyboard() -> InlineKeyboardMarkup:
    """
    Creates the inline keyboard for class selection.
    """
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="Class 10th", callback_data="class:10th"),
        InlineKeyboardButton(text="Class 11th", callback_data="class:11th")
    )
    builder.row(
        InlineKeyboardButton(text="Class 12th", callback_data="class:12th")
    )
    builder.row(
        InlineKeyboardButton(text="NEET", callback_data="class:neet"),
        InlineKeyboardButton(text="JEE", callback_data="class:jee")
    )
    
    return builder.as_markup()

def get_channel_join_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    """
    Creates a simple button to link to the channel.
    """
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="➡️ Join Channel", 
            url=f"https://t.me/{channel_username.lstrip('@')}"
        )
    )
    builder.add(
        InlineKeyboardButton(
            text="✅ Joined",
            callback_data="check_join"
        )
    )
    return builder.as_markup()

def get_payment_options_keyboard() -> InlineKeyboardMarkup:
    """
    Creates the inline keyboard for payment options.
    """
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="Paytm", callback_data="pay:paytm"),
        InlineKeyboardButton(text="G Pay", callback_data="pay:gpay"),
        InlineKeyboardButton(text="Other UPI", callback_data="pay:upi")
    )
    
    return builder.as_markup()

def get_pdf_deletion_keyboard(pdf_list: List[Tuple[int, str]]) -> InlineKeyboardMarkup:
    """
    Creates a keyboard with a list of PDFs to delete.
    """
    builder = InlineKeyboardBuilder()
    
    for pdf_id, title in pdf_list:
        short_title = (title[:40] + '...') if len(title) > 40 else title
        builder.row(
            InlineKeyboardButton(
                text=f"ID: {pdf_id} | {short_title}", 
                callback_data=f"del_select:{pdf_id}"
            )
        )
    
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="del_cancel"))
    return builder.as_markup()

def get_delete_confirmation_keyboard(pdf_id: int) -> InlineKeyboardMarkup:
    """
    Creates a final "Yes/No" confirmation keyboard for deletion.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Yes, Delete It", callback_data=f"del_confirm:{pdf_id}"),
        InlineKeyboardButton(text="❌ No, Cancel", callback_data="del_cancel")
    )
    return builder.as_markup()