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
from bot.db.pdf_queries import PdfResult
from typing import List

router = Router()
PAGE_SIZE = 5  # Number of results per page

# --- Helper function to build the keyboard ---
def create_pdf_keyboard(
    results: List[PdfResult],
    is_premium: bool,
    current_page: int,
    total_pages: int,
    query: str
) -> InlineKeyboardBuilder:
    """
    Creates an inline keyboard with PDF results and pagination.
    """
    builder = InlineKeyboardBuilder()

    # --- Add PDF result buttons ---
    for pdf in results:
        is_locked = (not pdf.is_free) and (not is_premium)
        
        # Truncate long titles
        title_display = pdf.title if len(pdf.title) <= 50 else pdf.title[:47] + "..."
        
        if is_locked:
            button_text = f"🔒 {title_display}"
            callback_data = f"pdf_lock:{pdf.pdf_id}"
        else:
            button_text = f"📄 {title_display}"
            callback_data = f"pdf_get:{pdf.pdf_id}"
        
        builder.row(InlineKeyboardButton(text=button_text, callback_data=callback_data))

    # --- Add Pagination Buttons ---
    if total_pages > 1:
        nav_buttons = []
        
        if current_page > 1:
            prev_page = f"pdf_page:{current_page - 1}:{query}"
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=prev_page))
        
        # Page indicator (non-clickable)
        nav_buttons.append(
            InlineKeyboardButton(
                text=f"• {current_page}/{total_pages} •", 
                callback_data="noop"
            )
        )

        if current_page < total_pages:
            next_page = f"pdf_page:{current_page + 1}:{query}"
            nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=next_page))
        
        builder.row(*nav_buttons)
    
    # Add a "New Search" button
    builder.row(InlineKeyboardButton(text="🔄 New Search", callback_data="pdf_new_search"))
    
    return builder

# --- 1. Trigger the search (from command or button) ---
@router.message(Command("search"), StateFilter('*'))
@router.message(F.text == "🔎 Search for pdf", StateFilter('*'))
async def start_search(message: Message, state: FSMContext, db_pool):
    """Initiate PDF search flow"""
    user_id = message.from_user.id
    await user_queries.update_user_last_active(db_pool, user_id)
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer(
            "❌ Please type /start to register first.",
            reply_markup=None
        )
        return
    
    # Check if user has selected a class
    if user.selected_class == "none":
        await message.answer(
            "❌ <b>Class Not Selected</b>\n\n"
            "Please select your class first using /changeclass before searching for PDFs."
        )
        return
    
    # Check download limit for free users
    if not user.is_premium and user.pdf_downloads_remaining <= 0:
        await message.answer(
            "❌ <b>PDF Download Limit Reached</b>\n\n"
            "You have used all your free PDF downloads for this month.\n\n"
            "💡 <b>Upgrade to Premium:</b>\n"
            "• 50 PDF downloads per day\n"
            "• Unlimited access to locked PDFs\n"
            "• 100 AI queries per day\n\n"
            "Use /upgrade to get premium access!"
        )
        return

    # Set the state and ask for the query
    await state.set_state(UserFlow.AwaitingSearchQuery)
    
    search_tips = (
        "🔍 <b>PDF Search</b>\n\n"
        "Send me your search query to find PDFs in your class.\n\n"
        f"<b>Your Class:</b> {user.selected_class.upper()}\n"
    )
    
    if not user.is_premium:
        search_tips += f"<b>Downloads Remaining:</b> {user.pdf_downloads_remaining}/10\n"
    
    search_tips += (
        "\n<b>Search Tips:</b>\n"
        "• Use specific keywords (e.g., 'physics chapter 1')\n"
        "• Try subject names (e.g., 'chemistry')\n"
        "• Use chapter numbers (e.g., 'chapter 5')\n\n"
        "Type /stop to cancel."
    )
    
    await message.answer(search_tips)

# --- 2. Handle the user's text query ---
@router.message(UserFlow.AwaitingSearchQuery)
async def handle_search_query(message: Message, state: FSMContext, db_pool):
    """Process the search query and display results"""
    query = message.text.strip()
    user_id = message.from_user.id
    
    # Validate query length
    if len(query) < 2:
        await message.answer(
            "❌ <b>Query Too Short</b>\n\n"
            "Please enter at least 2 characters to search.\n"
            "Type /stop to cancel."
        )
        return
    
    if len(query) > 100:
        await message.answer(
            "❌ <b>Query Too Long</b>\n\n"
            "Please keep your search query under 100 characters.\n"
            "Type /stop to cancel."
        )
        return
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer("❌ An error occurred. Please type /start.")
        await state.clear()
        return

    # Show searching indicator
    search_msg = await message.answer(
        f"🔍 Searching for '<b>{query}</b>' in <b>{user.selected_class}</b> PDFs...\n\n"
        "Please wait..."
    )
    
    # --- Perform Search ---
    try:
        results, total_pages = await pdf_queries.search_pdfs(
            db_pool, 
            user.selected_class, 
            user.is_premium, 
            query, 
            page=1, 
            page_size=PAGE_SIZE
        )
    except Exception as e:
        logging.error(f"PDF search error for user {user_id}: {e}")
        await search_msg.edit_text(
            "❌ <b>Search Error</b>\n\n"
            "An error occurred while searching. Please try again later."
        )
        await state.clear()
        return

    # Delete the searching message
    try:
        await search_msg.delete()
    except:
        pass

    if not results:
        no_results_msg = (
            f"❌ <b>No Results Found</b>\n\n"
            f"I couldn't find any PDFs matching '<b>{query}</b>' in <b>{user.selected_class}</b>.\n\n"
            "<b>Suggestions:</b>\n"
            "• Try different keywords\n"
            "• Use more general terms\n"
            "• Check for spelling mistakes\n"
            "• Try searching by subject name\n\n"
            "Type another query or /stop to cancel."
        )
        await message.answer(no_results_msg)
        # Keep them in the search state so they can try again
        return

    # --- Send Results ---
    keyboard = create_pdf_keyboard(results, user.is_premium, 1, total_pages, query)
    
    # Count locked vs unlocked
    locked_count = sum(1 for pdf in results if not pdf.is_free)
    unlocked_count = len(results) - locked_count
    
    result_header = (
        f"✅ <b>Search Results for '{query}'</b>\n\n"
        f"<b>Class:</b> {user.selected_class.upper()}\n"
        f"<b>Results:</b> Page 1 of {total_pages}\n"
    )
    
    if not user.is_premium and locked_count > 0:
        result_header += (
            f"\n🔒 <b>{locked_count}</b> locked PDF(s) found.\n"
            "Upgrade to premium to unlock all PDFs! (/upgrade)\n"
        )
    
    result_header += "\n<i>Click on a PDF to download:</i>"
    
    await message.answer(
        result_header,
        reply_markup=keyboard.as_markup()
    )
    
    # Clear the state since search is complete
    await state.clear()
    
    logging.info(f"User {user_id} searched for '{query}', found {len(results)} results")

# --- 3. Handle Pagination Clicks ---
@router.callback_query(F.data.startswith("pdf_page:"))
async def handle_pagination(callback: CallbackQuery, db_pool):
    """Handle pagination button clicks"""
    try:
        # Format: "pdf_page:{page_number}:{query}"
        parts = callback.data.split(":", 2)
        if len(parts) != 3:
            await callback.answer("Invalid pagination data", show_alert=True)
            return
        
        _, page_str, query = parts
        page = int(page_str)
        
        user = await user_queries.get_user(db_pool, callback.from_user.id)
        if not user:
            await callback.answer("Error: User not found", show_alert=True)
            return
        
        # Fetch the new page
        results, total_pages = await pdf_queries.search_pdfs(
            db_pool, 
            user.selected_class, 
            user.is_premium, 
            query, 
            page=page, 
            page_size=PAGE_SIZE
        )
        
        if not results:
            await callback.answer("No results found for this page", show_alert=True)
            return
        
        keyboard = create_pdf_keyboard(results, user.is_premium, page, total_pages, query)
        
        # Update the message with new results
        result_header = (
            f"✅ <b>Search Results for '{query}'</b>\n\n"
            f"<b>Class:</b> {user.selected_class.upper()}\n"
            f"<b>Results:</b> Page {page} of {total_pages}\n\n"
            "<i>Click on a PDF to download:</i>"
        )
        
        await callback.message.edit_text(
            result_header,
            reply_markup=keyboard.as_markup()
        )
        
        await callback.answer(f"Page {page} of {total_pages}")
        
    except ValueError:
        await callback.answer("Invalid page number", show_alert=True)
    except Exception as e:
        logging.error(f"Pagination error: {e}")
        await callback.answer("An error occurred", show_alert=True)

# --- 4. Handle "noop" (page indicator) clicks ---
@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery):
    """Handle clicks on non-interactive buttons"""
    await callback.answer()

# --- 5. Handle "New Search" button ---
@router.callback_query(F.data == "pdf_new_search")
async def handle_new_search(callback: CallbackQuery, state: FSMContext, db_pool):
    """Start a new search"""
    await callback.message.delete()
    await start_search(callback.message, state, db_pool)
    await callback.answer("Starting new search...")

# --- 6. Handle Locked PDF Clicks ---
@router.callback_query(F.data.startswith("pdf_lock:"))
async def handle_locked_pdf(callback: CallbackQuery):
    """Handle clicks on locked PDFs"""
    await callback.answer(
        "🔒 This PDF is locked!\n\n"
        "Upgrade to premium to access all locked PDFs.\n"
        "Use /upgrade to learn more.",
        show_alert=True
    )

# --- 7. Handle PDF Download (Unlocked PDFs) ---
@router.callback_query(F.data.startswith("pdf_get:"))
async def send_pdf_link(callback: CallbackQuery, db_pool):
    """Send the PDF download link to the user"""
    user_id = callback.from_user.id
    user = await user_queries.get_user(db_pool, user_id)
    
    if not user:
        await callback.answer("Error: User not found", show_alert=True)
        return
    
    # --- Check download limit for free users ---
    if not user.is_premium:
        if user.pdf_downloads_remaining <= 0:
            await callback.answer(
                "❌ You are out of PDF downloads!\n\n"
                "Use /upgrade to get 50 downloads per day.",
                show_alert=True
            )
            return
        
        # Decrement their limit
        success = await user_queries.decrement_pdf_download_limit(db_pool, user_id)
        if not success:
            await callback.answer(
                "❌ Download limit reached or error occurred.",
                show_alert=True
            )
            return
    
    # --- Get and send the PDF link ---
    pdf_id = int(callback.data.split(":")[1])
    link = await pdf_queries.get_pdf_link_by_id(db_pool, pdf_id)
    
    if link:
        # Get updated user info to show remaining downloads
        updated_user = await user_queries.get_user(db_pool, user_id)
        
        download_msg = (
            f"📥 <b>Download Link Ready!</b>\n\n"
            f"<a href='{link}'>Click here to download your PDF</a>\n\n"
        )
        
        if not updated_user.is_premium:
            download_msg += (
                f"<b>Downloads Remaining:</b> {updated_user.pdf_downloads_remaining}/10\n\n"
                "💡 Upgrade to premium for 50 daily downloads!"
            )
        else:
            download_msg += "✨ Enjoying premium? Thank you for your support!"
        
        await callback.message.answer(
            download_msg,
            disable_web_page_preview=True
        )
        
        if not user.is_premium:
            await callback.answer(
                f"✅ Link sent! {updated_user.pdf_downloads_remaining} downloads left",
                show_alert=False
            )
        else:
            await callback.answer("✅ Link sent!", show_alert=False)
        
        logging.info(f"User {user_id} downloaded PDF {pdf_id}")
    else:
        await callback.answer(
            "❌ Sorry, that file could not be found.\n"
            "It may have been removed from the database.",
            show_alert=True
        )
        logging.error(f"PDF {pdf_id} not found in database")