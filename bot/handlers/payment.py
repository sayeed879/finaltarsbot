import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

# Import your queries
from bot.db import user_queries
from bot.config import ADMIN_ID
from bot.fsm.states import UserFlow
from bot.keyboards.inline import get_payment_options_keyboard
from bot.keyboards.reply import get_main_menu_keyboard

# Initialize router
router = Router()

# Payment configuration
UPGRADE_PRICE = "199"
PAYMENT_QR_CODE_FILE_ID = "AgACAgUAAxkDAAINimkJzjyfC-qKRd9Ao9XvA_ZGpeQiAAL3C2sb6OtQVC1WyTarTeCCAQADAgADeQADNgQ"

PAYMENT_MESSAGE_TEXT = f"""
<b>💎 Upgrade to Premium Access! 💎</b>

<b>🎯 Premium Plan Details:</b>
<b>Price:</b> ₹{UPGRADE_PRICE} for 30 days
<b>Renewal:</b> Manual (we'll remind you before expiry)

<b>✨ What You Get with Premium:</b>

<b>📚 PDF Access:</b>
• Download up to <b>50 PDFs per day</b> (resets daily at 00:00 UTC)
• <b>All locked PDFs unlocked</b> 🔓 - No restrictions!

<b>🤖 AI Features:</b>
. • Enjoy <b>100 AI queries per day</b> (10x more than free users)
• Priority access to AI features 🚀

<b>🛠️ Custom Tools:</b>
• Access exclusive tools and features

<b>💳 Payment Methods:</b>
Click a button below to get the payment QR code for your preferred method.

<i>⚠️ After paying, please send a screenshot of your payment confirmation to activate your premium subscription.</i>
"""
# --- 1. Start upgrade process ---
@router.message(Command(commands=["upgrade"]), StateFilter('*')) # <-- CHANGED
@router.message(F.text == "💎 Access premium content", StateFilter('*')) # <-- CHANGED
async def start_upgrade(message: Message, db_pool, state: FSMContext): # <-- ADD 'state'
    """Handles the /upgrade command or premium access button - works from ANY state"""
    await state.clear() # <-- ADD THIS LINE
    user_id = message.from_user.id
    
    try:
        await user_queries.update_user_last_active(db_pool, user_id)
    except Exception as e:
        logging.warning(f"Could not update last_active: {e}")

    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer(
            "❌ Please type /start to register first.",
            reply_markup=None
        )
        return
    
    # Check if already premium
    if user.is_premium:
        expiry_date = user.premium_expiry_date.strftime("%B %d, %Y at %H:%M UTC")
        
        premium_status_msg = (
            "✨ <b>You are already a Premium User!</b> ✨\n\n"
            f"<b>Plan Status:</b> Active 💎\n"
            f"<b>Expires On:</b> {expiry_date}\n\n"
            "<b>Your Current Benefits:</b>\n"
            "✅ 100 AI queries per day\n"
            "✅ 50 PDF downloads per day\n"
            "✅ All locked PDFs unlocked\n"
            "✅ Priority support\n\n"
            "Use /stats to check your usage.\n\n"
            "<i>Your subscription will expire in a few days. We'll send you a reminder!</i>"
        )
        await message.answer(premium_status_msg, reply_markup=get_main_menu_keyboard())
        return

    # Show upgrade options
    await message.answer(
        PAYMENT_MESSAGE_TEXT,
        reply_markup=get_payment_options_keyboard(),
        disable_web_page_preview=True
    )
    
    logging.info(f"User {user_id} requested upgrade information")

# --- 2. Handle payment button (FIXED: Proper QR code sending) ---
@router.callback_query(F.data.startswith("pay:"))
async def send_payment_details(callback: CallbackQuery, state: FSMContext, db_pool, bot: Bot):
    """Sends payment QR code and moves user to screenshot state - FIXED VERSION"""
    try:
        user_id = callback.from_user.id
        username = callback.from_user.username or "N/A"
        first_name = callback.from_user.first_name or "User"

        # Update last active status
        try:
            await user_queries.update_user_last_active(db_pool, user_id)
        except Exception as e:
            logging.warning(f"Could not update last_active: {e}")
        
        # Extract payment method from callback data
        payment_method = callback.data.split(":")[1].upper()

        # Detailed payment instructions
        payment_caption = f"""
<b>💳 Payment Instructions</b>

<b>Selected Method:</b> {payment_method}
<b>Amount to Pay:</b> ₹{UPGRADE_PRICE}

<b>📱 How to Pay:</b>

<b>Step 1:</b> Scan the QR code below using any UPI app
<b>Step 2:</b> Enter amount: <b>₹{UPGRADE_PRICE}</b>
<b>Step 3:</b> Complete the payment
<b>Step 4:</b> Take a screenshot of the payment confirmation
<b>Step 5:</b> Send the screenshot back to me

<b>⚠️ IMPORTANT VERIFICATION DETAILS:</b>
These details will help us verify your payment faster:

<b>Your User ID:</b> <code>{user_id}</code>
<b>Your Username:</b> @{username}
<b>Your Name:</b> {first_name}
<b>Expected Amount:</b> ₹{UPGRADE_PRICE}

<b>💡 Pro Tips:</b>
• Make sure the screenshot clearly shows:
  - Payment amount (₹{UPGRADE_PRICE})
  - Transaction status (Success/Completed)
  - Date and time of payment
  - Transaction ID (if visible)
• Don't close this chat - wait for the payment to complete first
• Screenshot must be clear and readable

<b>🆘 Need Help?</b>
If you face any issues, type /help or contact our support.

<i>⏳ Waiting for your payment screenshot...</i>
"""

        # FIXED: Send payment QR code directly to user (not as reply to callback)
        try:
            await bot.send_photo(
                chat_id=user_id,
                photo=PAYMENT_QR_CODE_FILE_ID,
                caption=payment_caption,
                parse_mode="HTML"
            )
            logging.info(f"✅ Successfully sent QR code to user {user_id}")
        except Exception as e:
            logging.error(f"❌ Failed to send QR code to user {user_id}: {e}")
            await callback.message.answer(
                "❌ <b>Error Sending QR Code</b>\n\n"
                "There was an error sending the payment QR code. "
                "Please try /upgrade again or contact support."
            )
            await callback.answer("Error sending QR code", show_alert=True)
            return

        # Set state to await screenshot
        await state.set_state(UserFlow.AwaitingScreenshot)
        await callback.answer(f"QR code sent! Pay ₹{UPGRADE_PRICE} and send screenshot.", show_alert=False)
        
        # Update the original message
        await callback.message.edit_text(
            f"✅ <b>Payment QR Code Sent!</b>\n\n"
            f"Check the message above and follow the instructions.\n\n"
            f"<b>Selected Method:</b> {payment_method}\n"
            f"<b>Amount:</b> ₹{UPGRADE_PRICE}\n\n"
            f"After paying, send me a screenshot of your payment confirmation."
        )
        
        logging.info(f"User {user_id} ({username}) requested payment QR via {payment_method}")
    
    except Exception as e:
        logging.exception(f"Error in send_payment_details: {e}")
        await callback.message.answer(
            "❌ <b>Error</b>\n\n"
            "Sorry, there was an error processing your request. Please try /upgrade again."
        )
        await callback.answer("Error occurred", show_alert=True)

# --- 3. Handle payment screenshot ---
@router.message(UserFlow.AwaitingScreenshot, F.photo)
async def handle_screenshot(message: Message, bot: Bot, state: FSMContext, db_pool):
    """Handles user's payment screenshot and forwards it to the admin"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username or "N/A"
        first_name = message.from_user.first_name or "User"
        
        try:
            await user_queries.update_user_last_active(db_pool, user_id)
        except Exception as e:
            logging.warning(f"Could not update last_active: {e}")

        # Detailed admin notification
        admin_notification = (
            "<b>🔔 NEW PAYMENT VERIFICATION REQUEST</b>\n\n"
            "<b>👤 User Information:</b>\n"
            f"• Name: {first_name}\n"
            f"• Username: @{username}\n"
            f"• User ID: <code>{user_id}</code>\n\n"
            "<b>💳 Payment Details:</b>\n"
            f"• Expected Amount: ₹{UPGRADE_PRICE}\n"
            f"• Plan Duration: 30 days\n"
            f"• Submitted: {message.date.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            "<b>⚡ Quick Actions:</b>\n"
            f"• Approve: /upgradeuser {user_id}\n"
            f"• Reject: Send message to {user_id}\n"
            f"• Check Stats: /stats\n\n"
            "<b>📸 Payment Screenshot:</b>\n"
            "(See forwarded message below)"
        )

        # Send notification to admin
        await bot.send_message(
            ADMIN_ID,
            admin_notification,
            parse_mode="HTML"
        )
        
        # Forward the screenshot
        await bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user_id,
            message_id=message.message_id
        )

        # Detailed user confirmation
        user_confirmation = (
            "✅ <b>Screenshot Received Successfully!</b>\n\n"
            "<b>What Happens Next:</b>\n\n"
            "<b>⏰ Verification Time:</b> Usually 1-24 hours\n"
            "<b>🔔 Notification:</b> You'll get a message when approved\n"
            "<b>💎 Activation:</b> Instant after admin approval\n\n"
            "<b>📋 Your Submission Details:</b>\n"
            f"• User ID: <code>{user_id}</code>\n"
            f"• Submitted At: {message.date.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"• Payment Amount: ₹{UPGRADE_PRICE}\n"
            f"• Plan Duration: 30 days\n\n"
            "<b>✨ After Approval You'll Get:</b>\n"
            "• 100 AI queries per day (10x increase!)\n"
            "• 50 PDF downloads per day (5x increase!)\n"
            "• All locked PDFs unlocked 🔓\n"
            "• Priority support\n\n"
            "<b>💡 Important Notes:</b>\n"
            "• Our admin will verify your payment manually\n"
            "• You'll receive a confirmation message once approved\n"
            "• If there's any issue, admin will contact you\n"
            "• Keep this chat open to receive your approval notification\n\n"
            "<b>🆘 Questions?</b>\n"
            "Type /help for support or wait for admin response.\n\n"
            "<i>Thank you for upgrading! We appreciate your support. 🙏</i>"
        )
        
        await message.answer(user_confirmation, parse_mode="HTML")
        
        # Clear FSM state
        await state.clear()
        
        logging.info(f"Payment screenshot received from user {user_id} ({username})")

    except Exception as e:
        logging.exception(f"Error in handle_screenshot: {e}")
        await message.answer(
            "❌ <b>Error</b>\n\n"
            "Sorry, there was an error processing your screenshot. "
            "Please try sending it again or contact support with /help.",
            parse_mode="HTML"
        )

# --- 4. Handle invalid input (non-photo) ---
@router.message(UserFlow.AwaitingScreenshot, ~F.photo)
async def invalid_screenshot(message: Message):
    """Informs user if they send a non-photo during payment verification"""
    await message.answer(
        f"❌ <b>Invalid Format</b>\n\n"
        f"Please send a <b>photo/screenshot</b> of your payment confirmation.\n\n"
        f"<b>What to include in the screenshot:</b>\n"
        f"• Payment amount (₹{UPGRADE_PRICE})\n"
        f"• Transaction status (Success/Completed)\n"
        f"• Date and time\n"
        f"• Transaction ID (if available)\n\n"
        f"💡 <i>Tip: Use your phone's screenshot feature to capture the payment confirmation screen.</i>\n\n"
        f"Type /stop to cancel the payment process.",
        parse_mode="HTML"
    )

# --- 5. Check payment status ---
@router.message(Command(commands=["paymentstatus"]), StateFilter(None))
async def check_payment_status(message: Message, db_pool):
    """Allow users to check their payment/premium status"""
    user_id = message.from_user.id
    
    user = await user_queries.get_user(db_pool, user_id)
    
    if not user:
        await message.answer("❌ Please type /start first.")
        return
    
    if user.is_premium:
        expiry_date = user.premium_expiry_date.strftime("%B %d, %Y at %H:%M UTC")
        await message.answer(
            "✨ <b>Premium Status: Active</b> ✨\n\n"
            f"<b>Expires On:</b> {expiry_date}\n\n"
            "Use /stats to see your usage details.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "👤 <b>Current Status: Free User</b>\n\n"
            "You are currently on the free plan.\n\n"
            "Upgrade to premium for:\n"
            "• 100 AI queries per day\n"
            "• 50 PDF downloads per day\n"
            "• All PDFs unlocked\n\n"
            "Use /upgrade to get premium access!",
            parse_mode="HTML"
        )