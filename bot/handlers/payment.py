import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

# Our component imports
from bot.config import ADMIN_ID
from bot.fsm.states import UserFlow
from bot.keyboards.inline import get_payment_options_keyboard
from bot.db import user_queries

router = Router()

# Define your payment info
UPGRADE_PRICE = "199"
PAYMENT_MESSAGE_TEXT = f"""
<b>💎 Get Premium Access! 💎</b>

Upgrade for just <b>₹{UPGRADE_PRICE} for 30 days</b> and get:

✅ <b>100</b> Daily AI Queries
✅ <b>50</b> Daily PDF Searches
✅ All locked PDFs <b>unlocked</b>!
✅ Priority support

Click a button below to get the payment QR code.
"""

PAYMENT_QR_CODE_FILE_ID = "AgACAgUAAxkBAAEYsCBpBKYY1sBTMkWbLvrCDyaE2HgQGAACAw9rGwvQKFQFpXe3ZEZeWAEAAwIAA3kAAzYE" # IMPORTANT!

# --- 1. Trigger the upgrade (from command or button) ---
@router.message(Command(commands=["upgrade"]))
@router.message(F.text == "💎 Access premium content")
async def start_upgrade(message: Message, db_pool):
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

# --- 2. Handle the payment button click (e.g., "Paytm") ---
@router.callback_query(F.data.startswith("pay:"))
async def send_payment_details(callback: CallbackQuery, fsm_context: FSMContext):
    
    # IMPORTANT: You must get this file_id first.
    # 1. Send your QR code image to your bot in a private chat.
    # 2. The bot will send you a JSON error (since no handler is set).
    # 3. In that JSON, find the "photo" section, and get the "file_id"
    #    (it's a long string).user_id = callback.from_user.id
    user_id = callback.from_user.id
    username = callback.from_user.username or "N/A"
    
    # Send the QR code
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
    
    # Set the user's state to wait for their screenshot
    await fsm_context.set_state(UserFlow.AwaitingScreenshot)
    
    await callback.answer("Please send your screenshot.")
    # Edit the original message to remove the buttons
    await callback.message.edit_text("QR code sent. Please check your chat.")

# --- 3. Handle the screenshot ---
@router.message(UserFlow.AwaitingScreenshot, F.photo)
async def handle_screenshot(message: Message, bot: Bot, fsm_context: FSMContext, db_pool):
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    
    await user_queries.update_user_last_active(db_pool, user_id)
    
    # 1. Forward the screenshot to the Admin
    try:
        await bot.send_message(
            ADMIN_ID,
            f"<b>New Payment Verification:</b>\n\n"
            f"<b>User:</b> @{username}\n"
            f"<b>User ID:</b> `{user_id}`\n\n"
            f"Use this command to approve:\n"
            f"`/upgradeuser {user_id}`"
        )
        # Forward the actual photo
        await bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user_id,
            message_id=message.message_id
        )
    except Exception as e:
        logging.error(f"Failed to forward screenshot to admin: {e}")
        await message.answer(
            "Sorry, there was an error sending your screenshot to the admin. "
            "Please contact support."
        )
        return

    # 2. Inform the user
    await message.answer(
        "✅ Thank you! I have sent your screenshot to the admin for verification. "
        "This may take some time. I will notify you once you are approved."
    )
    
    # 3. Clear the user's state
    await fsm_context.clear()

# --- 4. Handle non-photo messages in screenshot state ---
@router.message(UserFlow.AwaitingScreenshot)
async def invalid_screenshot(message: Message):
    await message.answer(
        "That's not a photo. Please send a screenshot of your payment, "
        "or type /stop to cancel."
    )
