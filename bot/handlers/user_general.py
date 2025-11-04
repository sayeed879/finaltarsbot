import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

# Our component imports
from bot.keyboards.reply import get_main_menu_keyboard
from bot.db import user_queries
from bot.fsm.states import UserFlow, AdminFlow

# Initialize router
router = Router()

#
@router.message(Command("stop"), StateFilter('*'))  #
async def handle_stop(message: Message, state: FSMContext, db_pool):
    """Cancel any active operation and return to main menu"""
    user_id = message.from_user.id

    # Update last active time
    await user_queries.update_user_last_active(db_pool, user_id)

    # Get the current FSM state
    current_state = await state.get_state()

    if current_state:
        # Clear FSM
        await state.clear()

        # Detect which process was cancelled
        state_messages = {
            UserFlow.AwaitingClassSelection: "Class selection",
            UserFlow.AwaitingSearchQuery: "PDF search",
            UserFlow.AwaitingAIPrompt: "AI chat",
            UserFlow.AwaitingScreenshot: "Payment process",
            AdminFlow.AwaitingBroadcastMessage: "Broadcast message",
            AdminFlow.AddPDF_AwaitingTitle: "PDF upload"
        }

        operation = "operation"
        for st, msg in state_messages.items():
            if current_state == st.state:
                operation = msg
                break

        await message.answer(
            f"🛑 <b>{operation.title()} Cancelled</b>\n\n"
            "You are now back in the main menu.\n\n"
            "Use the buttons below or type /help for assistance.",
            reply_markup=get_main_menu_keyboard()
        )

    else:
        await message.answer(
            "ℹ️ <b>No Active Operation</b>\n\n"
            "You weren't in any active process.\n\n"
            "Here's the main menu:",
            reply_markup=get_main_menu_keyboard()
        )

# --- Handler for the /help command ---
@router.message(Command("help"), StateFilter('*'))
@router.message(F.text == "🆘 /help")
async def handle_help(message: Message, db_pool):
    """Show help message with all available commands"""
    await user_queries.update_user_last_active(db_pool, message.from_user.id)
    
    help_text = (
        "<b>📚 Bot Help & Commands</b>\n\n"
        "<b>🎯 Main Commands:</b>\n"
        "• /start - Start or restart the bot\n"
        "• /stop - Cancel any current operation\n"
        "• /help - Show this help message\n\n"

        "<b>⚙️ Account Management:</b>\n"
        "• /changeclass - Change your selected class\n"
        "• /stats - Check your account status and limits\n"
        "• /upgrade - Upgrade to premium access\n\n"

        "<b>📖 Features:</b>\n"
        "• /search or 🔎 Button - Search for PDFs in your class\n"
        "• 💬 Button - Chat with AI assistant\n"
        "• 💎 Button - Learn about premium features\n\n"
        
        "<b>💡 Tips:</b>\n"
        "• Free users get 10 AI queries per day and 10 PDF downloads per month\n"
        "• Premium users get 100 AI queries and 50 PDF downloads per day\n"
        "• Use specific keywords when searching for PDFs\n"
        "• Type /stop anytime to cancel an operation\n\n"
        
        "<b>🆘 Need More Help?</b>\n"
        "Contact our support team or check the premium benefits with /upgrade.\n\n"
        
        "<i>Use the buttons below for quick access to features!</i>"
    )
    
    await message.answer(help_text, reply_markup=get_main_menu_keyboard())

# --- Handler for the user's /stats command ---
@router.message(Command("stats"), StateFilter('*'))
async def handle_stats(message: Message, db_pool):
    """Show user's account statistics and limits"""
    user_id = message.from_user.id
    await user_queries.update_user_last_active(db_pool, user_id)
    
    user = await user_queries.get_user(db_pool, user_id)
    
    if not user:
        await message.answer(
            "❌ <b>Not Registered</b>\n\n"
            "Please type /start to register first."
        )
        return

    # Calculate days until expiry for premium users
    days_remaining = ""
    if user.is_premium and user.premium_expiry_date:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        delta = user.premium_expiry_date - now
        days = delta.days
        hours = delta.seconds // 3600
        
        if days > 0:
            days_remaining = f"\n<b>Time Remaining:</b> {days} days, {hours} hours"
        elif days == 0:
            days_remaining = f"\n<b>Time Remaining:</b> {hours} hours ⚠️"
        else:
            days_remaining = "\n<b>Status:</b> ⚠️ <i>Expired - will be downgraded soon</i>"

    # Format the stats message
    if user.is_premium:
        status_emoji = "💎"
        status_text = "Premium User"
        expiry_date = user.premium_expiry_date.strftime("%B %d, %Y at %H:%M UTC")
        plan_info = (
            f"<b>Plan Expires:</b> {expiry_date}"
            f"{days_remaining}\n"
        )
        limits_header = "<b>📊 Premium Limits (Resets Daily at 00:00 UTC):</b>"
    else:
        status_emoji = "👤"
        status_text = "Free User"
        plan_info = (
            "<b>Plan:</b> Free Tier\n"
            "<b>Upgrade:</b> Use /upgrade to get premium!\n"
        )
        limits_header = "<b>📊 Free Tier Limits:</b>"

    stats_text = (
        f"<b>📊 Your Account Statistics</b>\n\n"
        f"<b>Status:</b> {status_emoji} {status_text}\n"
        f"<b>Class:</b> {user.selected_class.upper()}\n"
        f"<b>Username:</b> @{message.from_user.username or 'Not set'}\n"
        f"<b>User ID:</b> <code>{user_id}</code>\n\n"
        f"{plan_info}\n"
        f"{limits_header}\n"
    )
    
    # AI Limits
    if user.is_premium:
        ai_percentage = (user.ai_limit_remaining / 100) * 100
        ai_bar = "🟩" * (ai_percentage // 10) + "⬜" * (10 - (ai_percentage // 10))
        stats_text += (
            f"<b>🤖 AI Queries:</b> {user.ai_limit_remaining}/100 remaining\n"
            f"{ai_bar}\n\n"
        )
    else:
        ai_percentage = (user.ai_limit_remaining / 10) * 100
        ai_bar = "🟩" * (ai_percentage // 10) + "⬜" * (10 - (ai_percentage // 10))
        stats_text += (
            f"<b>🤖 AI Queries:</b> {user.ai_limit_remaining}/10 remaining (resets daily)\n"
            f"{ai_bar}\n\n"
        )
    
    # PDF Limits
    if user.is_premium:
        pdf_percentage = (user.pdf_downloads_remaining / 50) * 100
        pdf_bar = "🟦" * (pdf_percentage // 10) + "⬜" * (10 - (pdf_percentage // 10))
        stats_text += (
            f"<b>📄 PDF Downloads:</b> {user.pdf_downloads_remaining}/50 remaining\n"
            f"{pdf_bar}\n\n"
        )
    else:
        pdf_percentage = (user.pdf_downloads_remaining / 10) * 100
        pdf_bar = "🟦" * (pdf_percentage // 10) + "⬜" * (10 - (pdf_percentage // 10))
        stats_text += (
            f"<b>📄 PDF Downloads:</b> {user.pdf_downloads_remaining}/10 remaining (resets monthly)\n"
            f"{pdf_bar}\n\n"
        )
    
    # Additional info
    if not user.is_premium:
        stats_text += (
            "<b>💡 Want More?</b>\n"
            "Upgrade to premium for:\n"
            "• 100 AI queries per day (10x more!)\n"
            "• 50 PDF downloads per day (5x more!)\n"
            "• All locked PDFs unlocked 🔓\n"
            "• Priority support\n\n"
            "Use /upgrade to learn more!"
        )
    else:
        stats_text += (
            "<i>Thank you for being a premium member! 🙏</i>\n\n"
            "Your support helps us improve the bot."
        )
    
    await message.answer(stats_text)

# --- "About" trigger handler ---
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

# FIXED: Only catch text when NOT in any FSM state
@router.message(StateFilter(None), F.text)
async def handle_general_text(message: Message, db_pool):
    """
    Handle general text messages only when user is not in any FSM state.
    This prevents interference with ongoing operations.
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
    
    # Thanks
    elif (word in msg_text for word in ["thanks", "thank you", "thx"]):
        await message.answer(
            "You're welcome! 😊\n\n"
            "Happy to help. Let me know if you need anything else!\n\n"
            "Use /help if you have questions."
        )