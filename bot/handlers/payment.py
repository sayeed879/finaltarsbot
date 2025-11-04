import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

# Import your queries
from bot.db import user_queries

# --- Imports from your bot components ---
from bot.config import ADMIN_ID
from bot.fsm.states import UserFlow
from bot.keyboards.inline import get_payment_options_keyboard
from bot.db import user_queries

# --- Initialize router ---
router = Router()

# --- Payment configuration ---
UPGRADE_PRICE = "199"
PAYMENT_QR_CODE_FILE_ID = "AgACAgUAAxkDAAINimkJzjyfC-qKRd9Ao9XvA_ZGpeQiAAL3C2sb6OtQVC1WyTarTeCCAQADAgADeQADNgQ"

PAYMENT_MESSAGE_TEXT = f"""
<b>💎 Get Premium Access! 💎</b>

Upgrade for just <b>₹{UPGRADE_PRICE} for 30 days</b> and get:

✅ <b>100</b> Daily AI Queries
✅ <b>50</b> Daily PDF Searches
✅ All locked PDFs <b>unlocked</b>!
✅ Priority support

Click a button below to get the payment QR code.
"""

# --- 1. Start upgrade process ---
@router.message(Command(commands=["upgrade"]))
@router.message(F.text == "💎 Access premium content")
async def start_upgrade(message: Message, db_pool):
    """Handles the /upgrade command or premium access button."""
    try:
        await user_queries.update_user_last_active(db_pool, message.from_user.id)

        user = await user_queries.get_user(db_pool, message.from_user.id)
        if not user:
            await message.answer("Please type /start to register first.")
            return
        
        if user.is_premium:
            await message.answer("You are already a 💎 Premium User!")
            return

        await message.answer(
            PAYMENT_MESSAGE_TEXT,
            reply_markup=get_payment_options_keyboard()
        )

    except Exception as e:
        logging.exception(f"Error in start_upgrade: {e}")
        await message.answer("An error occurred while processing your request. Please try again later.")

# --- 2. Handle payment button (e.g., "Paytm") ---
@router.callback_query(F.data.startswith("pay:"))
async def send_payment_details(callback: CallbackQuery, state: FSMContext, db_pool):
    """Sends payment QR code and moves user to screenshot state."""
    try:
        user_id = callback.from_user.id
        username = callback.from_user.username or "N/A"

        # Update last active status using asyncpg
        await user_queries.update_user_last_active(db_pool, user_id)

        # Send payment QR code
        await callback.message.answer_photo(
            photo=PAYMENT_QR_CODE_FILE_ID,
            caption=f"""
Please pay <b>₹{UPGRADE_PRICE}</b> using the QR code.

<b>IMPORTANT:</b> After paying, please send the <b>screenshot</b> of your payment.

Your details for verification:
<b>User ID:</b> `{user_id}`
<b>Username:</b> @{username}
"""
        )

        await state.set_state(UserFlow.AwaitingScreenshot)
        await callback.answer("Please send your screenshot.")
        await callback.message.edit_text("QR code sent. Please check your chat.")
    
    except Exception as e:
        logging.exception(f"Error in send_payment_details: {e}")
        await callback.message.answer("Sorry, there was an error sending payment details. Please try again later.")

# --- 3. Handle payment screenshot ---
@router.message(UserFlow.AwaitingScreenshot, F.photo)
async def handle_screenshot(message: Message, bot: Bot, state: FSMContext, db_pool):
    """Handles user's payment screenshot and forwards it to the admin."""
    try:
        user_id = message.from_user.id
        username = message.from_user.username or "N/A"
        await user_queries.update_user_last_active(db_pool, user_id)

        # Send message to admin for verification
        await bot.send_message(
            ADMIN_ID,
            f"<b>New Payment Verification:</b>\n\n"
            f"<b>User:</b> @{username}\n"
            f"<b>User ID:</b> `{user_id}`\n\n"
            f"Use this command to approve:\n"
            f"`/upgradeuser {user_id}`"
        )
        await bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user_id,
            message_id=message.message_id
        )

        await message.answer(
            "✅ Thank you! I have sent your screenshot to the admin for verification. "
            "This may take some time. I will notify you once you are approved."
        )
        await state.clear()

    except Exception as e:
        logging.exception(f"Error in handle_screenshot: {e}")
        await message.answer("Sorry, there was an error sending your screenshot to the admin. Please try again later.")

# --- 4. Handle invalid input (non-photo) ---
@router.message(UserFlow.AwaitingScreenshot)
async def invalid_screenshot(message: Message):
    """Informs user if they send a non-photo during payment verification."""
    await message.answer(
        "That's not a photo. Please send a screenshot of your payment, "
        "or type /stop to cancel."
    )
