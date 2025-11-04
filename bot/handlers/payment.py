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

# ENHANCED: More detailed payment message
PAYMENT_MESSAGE_TEXT = f"""
<b>💎 Upgrade to Premium Access! 💎</b>

<b>🎯 Premium Plan Details:</b>
<b>Price:</b> ₹{UPGRADE_PRICE} for 30 days
<b>Renewal:</b> Manual (we'll remind you before expiry)

<b>✨ What You Get with Premium:</b>

<b>📚 PDF Access:</b>
• Download up to <b>50 PDFs per day</b> (resets daily at 00:00 UTC)
• <b>All locked PDFs unlocked</b> 🔓 - No restrictions!
• Access to exclusive premium-only materials
• Priority updates when new PDFs are added

<b>🤖 AI Features:</b>
• <b>100 AI queries per day</b> (10x more than free users)
• Faster AI response times
• Enhanced AI memory (remembers more context)
• Access to advanced AI features

<b>⚡ Other Benefits:</b>
• <b>Priority support</b> - Get help faster
• <b>No ads or promotional messages</b>
• Early access to new features
• Dedicated premium support channel

<b>📊 Your Current Status:</b>
• You are currently on the <b>Free Plan</b>
• Free users get: 10 AI queries/day, 10 PDF downloads/month
• Many PDFs are locked for free users 🔒

<b>💳 Payment Methods:</b>
Click a button below to get the payment QR code for your preferred method.

<i>⚠️ After paying, please send a screenshot of your payment confirmation to activate your premium subscription.</i>
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
            await message.answer(premium_status_msg)
            return

        # Show upgrade options
        await message.answer(
            PAYMENT_MESSAGE_TEXT,
            reply_markup=get_payment_options_keyboard(),
            disable_web_page_preview=True
        )

    except Exception as e:
        logging.exception(f"Error in start_upgrade: {e}")
        await message.answer(
            "❌ <b>Error</b>\n\n"
            "An error occurred while processing your request. Please try again later or contact support."
        )

# --- 2. Handle payment button (e.g., "Paytm") ---
@router.callback_query(F.data.startswith("pay:"))
async def send_payment_details(callback: CallbackQuery, state: FSMContext, db_pool):
    """Sends payment QR code and moves user to screenshot state."""
    try:
        user_id = callback.from_user.id
        username = callback.from_user.username or "N/A"
        first_name = callback.from_user.first_name or "User"

        # Update last active status
        await user_queries.update_user_last_active(db_pool, user_id)
        
        # Extract payment method from callback data
        payment_method = callback.data.split(":")[1].upper()

        # ENHANCED: Detailed payment instructions
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

<b>✅ What Happens Next:</b>
1. You send the payment screenshot
2. Our admin reviews it (usually within 1-24 hours)
3. Your account is upgraded to Premium immediately after verification
4. You receive a confirmation message with all premium features activated

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

        # Send payment QR code
        await callback.message.answer_photo(
            photo=PAYMENT_QR_CODE_FILE_ID,
            caption=payment_caption
        )

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
            "Sorry, there was an error sending payment details. Please try /upgrade again."
        )
        await callback.answer("Error occurred", show_alert=True)

# --- 3. Handle payment screenshot ---
@router.message(UserFlow.AwaitingScreenshot, F.photo)
async def handle_screenshot(message: Message, bot: Bot, state: FSMContext, db_pool):
    """Handles user's payment screenshot and forwards it to the admin."""
    try:
        user_id = message.from_user.id
        username = message.from_user.username or "N/A"
        first_name = message.from_user.first_name or "User"
        
        await user_queries.update_user_last_active(db_pool, user_id)

        # ENHANCED: Detailed admin notification
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
            admin_notification
        )
        
        # Forward the screenshot
        await bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user_id,
            message_id=message.message_id
        )

        # ENHANCED: Detailed user confirmation
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
        
        await message.answer(user_confirmation)
        
        # Clear FSM state
        await state.clear()
        
        logging.info(f"Payment screenshot received from user {user_id} ({username})")

    except Exception as e:
        logging.exception(f"Error in handle_screenshot: {e}")
        await message.answer(
            "❌ <b>Error</b>\n\n"
            "Sorry, there was an error processing your screenshot. "
            "Please try sending it again or contact support with /help."
        )

# --- 4. Handle invalid input (non-photo) ---
@router.message(UserFlow.AwaitingScreenshot)
async def invalid_screenshot(message: Message):
    """Informs user if they send a non-photo during payment verification."""
    await message.answer(
        "❌ <b>Invalid Format</b>\n\n"
        "Please send a <b>photo/screenshot</b> of your payment confirmation.\n\n"
        "<b>What to include in the screenshot:</b>\n"
        "• Payment amount (₹{UPGRADE_PRICE})\n"
        "• Transaction status (Success/Completed)\n"
        "• Date and time\n"
        "• Transaction ID (if available)\n\n"
        "💡 <i>Tip: Use your phone's screenshot feature to capture the payment confirmation screen.</i>\n\n"
        "Type /stop to cancel the payment process."
    )

# --- 5. Additional: Check payment status ---
@router.message(Command(commands=["paymentstatus"]))
async def check_payment_status(message: Message, db_pool):
    """Allow users to check their payment/premium status"""
    user = await user_queries.get_user(db_pool, message.from_user.id)
    
    if not user:
        await message.answer("❌ Please type /start first.")
        return
    
    if user.is_premium:
        expiry_date = user.premium_expiry_date.strftime("%B %d, %Y at %H:%M UTC")
        await message.answer(
            "✨ <b>Premium Status: Active</b> ✨\n\n"
            f"<b>Expires On:</b> {expiry_date}\n\n"
            "Use /stats to see your usage details."
        )
    else:
        await message.answer(
            "👤 <b>Current Status: Free User</b>\n\n"
            "You are currently on the free plan.\n\n"
            "Upgrade to premium for:\n"
            "• 100 AI queries per day\n"
            "• 50 PDF downloads per day\n"
            "• All PDFs unlocked\n\n"
            "Use /upgrade to get premium access!"
        )