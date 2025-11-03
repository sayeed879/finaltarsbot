import logging
import math
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# Our component imports
from bot.fsm.states import UserFlow
from bot.db import user_queries, pdf_queries
from bot.db.pdf_queries import PdfResult # Import our dataclass
from typing import List

router = Router()
PAGE_SIZE = 5 # Number of results per page

# --- Helper function to build the keyboard ---
def create_pdf_keyboard(
    results: List[PdfResult],
    is_premium: bool,
    current_page: int,
    total_pages: int,
    query: str
) -> InlineKeyboardBuilder:
    
    builder = InlineKeyboardBuilder()

    # --- Add PDF result buttons ---
    for pdf in results:
        is_locked = (not pdf.is_free) and (not is_premium)
        button_text = f"📄 {pdf.title} 🔒" if is_locked else f"📄 {pdf.title}"
        
        # We use a 'prefix' to know what to do with the button
        callback_data = f"pdf_lock:{pdf.pdf_id}" if is_locked else f"pdf_get:{pdf.pdf_id}"
        
        builder.row(InlineKeyboardButton(text=button_text, callback_data=callback_data))

    # --- Add Pagination Buttons ---
    if total_pages > 1:
        prev_page = f"pdf_page:{current_page - 1}:{query}"
        next_page = f"pdf_page:{current_page + 1}:{query}"
        
        nav_buttons = []
        if current_page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=prev_page))
        
        nav_buttons.append(
            InlineKeyboardButton(text=f"Page {current_page}/{total_pages}", callback_data="noop")
        )

        if current_page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=next_page))
            
        builder.row(*nav_buttons)
        
    return builder

# --- 1. Trigger the search (from command or button) ---
@router.message(Command(commands=["search"]))
@router.message(F.text == "🔎 Search for pdf")
async def start_search(message: Message, fsm_context: FSMContext, db_pool):
    user_id = message.from_user.id
    await user_queries.update_user_last_active(db_pool, user_id)
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer("Please type /start to register first.")
        return

    # Set the state and ask for the query
    await fsm_context.set_state(UserFlow.AwaitingSearchQuery)
    await message.answer("Please send me your search query (e.g., 'physics chapter 1').\nType /stop to cancel.")

# --- 2. Handle the user's text query ---
@router.message(UserFlow.AwaitingSearchQuery)
async def handle_search_query(message: Message, fsm_context: FSMContext, db_pool):
    query = message.text
    user_id = message.from_user.id
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer("An error occurred. Please type /start.")
        return

    # --- Decrement Limit ---
    # --- Perform Search ---
    results, total_pages = await pdf_queries.search_pdfs(
        db_pool, user.selected_class, user.is_premium, query, page=1, page_size=PAGE_SIZE
    )

    if not results:
        await message.answer("Sorry, I couldn't find any PDFs matching that query. Please try again.")
        # We leave them in the search state
        return

    # --- Send Results ---
    keyboard = create_pdf_keyboard(results, user.is_premium, 1, total_pages, query)
    await message.answer(
        f"Here are the results for '<b>{query}</b>':",
        reply_markup=keyboard.as_markup()
    )
    # We are done with this specific query, so we clear the state.
    await fsm_context.clear()

# --- 3. Handle Pagination Clicks ---
@router.callback_query(F.data.startswith("pdf_page:"))
async def handle_pagination(callback: CallbackQuery, db_pool):
    # Format: "pdf_page:{page_number}:{query}"
    _, page_str, query = callback.data.split(":", 2)
    page = int(page_str)
    
    user = await user_queries.get_user(db_pool, callback.from_user.id)
    
    results, total_pages = await pdf_queries.search_pdfs(
        db_pool, user.selected_class, user.is_premium, query, page=page, page_size=PAGE_SIZE
    )

    keyboard = create_pdf_keyboard(results, user.is_premium, page, total_pages, query)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard.as_markup())
    except Exception as e:
        logging.warning(f"Error editing message for pagination: {e}")

    await callback.answer()
@router.callback_query(F.data.startswith("pdf_get:"))
async def send_pdf_link(callback: CallbackQuery, db_pool):
    user_id = callback.from_user.id
    user = await user_queries.get_user(db_pool, user_id)

    # --- NEW LIMIT CHECK ---
    if not user.is_premium:
        if user.pdf_downloads_remaining <= 0:
            await callback.answer(
                "You are out of PDF download credits. Use /upgrade to get more.",
                show_alert=True
            )
            return

        # Decrement their limit
        await user_queries.decrement_pdf_download_limit(db_pool, user_id)

    # --- Proceed to send link ---
    pdf_id = int(callback.data.split(":")[1])
    link = await pdf_queries.get_pdf_link_by_id(db_pool, pdf_id)

    if link:
        await callback.message.answer(
            f"Here is your download link:\n{link}",
            disable_web_page_preview=True
        )
        await callback.answer("✅ Link sent! Download credit used.")
    else:
        await callback.answer("Sorry, that file could not be found.", show_alert=True)