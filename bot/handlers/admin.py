import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from typing import Optional, Tuple

# Our component imports
from bot.config import ADMIN_ID
from bot.fsm.states import AdminFlow
from bot.db import user_queries, pdf_queries
from bot.keyboards import inline as inline_keyboards

# --- Admin-Only Filter ---
class AdminFilter(Filter):
    async def __call__(self, event) -> bool:
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return False
        return user_id == ADMIN_ID

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

# --- Helper Function for Parsing Commands ---
def parse_command(text: str) -> Tuple[str, Optional[str]]:
    """
    Parses a command like '/cmd 123' or '/cmd <message>'.
    Returns (command, argument)
    """
    if ' ' not in text:
        return (text, None)
    
    command, argument = text.split(' ', 1)
    return (command, argument.strip())

# --- Admin: User Management ---

@router.message(Command(commands=["upgradeuser"]))
async def admin_upgrade_user(message: Message, bot: Bot, db_pool):
    """Upgrade a user to premium status"""
    command, arg = parse_command(message.text)
    
    # FIXED: Proper validation with helpful error message
    if not arg:
        await message.answer(
            "❌ <b>Invalid Usage</b>\n\n"
            "<b>Usage:</b> <code>/upgradeuser &lt;user_id&gt;</code>\n\n"
            "<b>Example:</b> <code>/upgradeuser 123456789</code>\n\n"
            "💡 <i>Tip: You can get the user ID from their payment screenshot message.</i>"
        )
        return
    
    if not arg.isdigit():
        await message.answer(
            "❌ <b>Invalid User ID</b>\n\n"
            f"'{arg}' is not a valid user ID. User IDs must be numbers only.\n\n"
            "<b>Example:</b> <code>/upgradeuser 123456789</code>"
        )
        return

    user_id = int(arg)
    
    # Check if user exists first
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer(
            f"❌ <b>User Not Found</b>\n\n"
            f"User ID <code>{user_id}</code> does not exist in the database.\n\n"
            "Make sure the user has started the bot at least once."
        )
        return
    
    # Check if already premium
    if user.is_premium:
        expiry = user.premium_expiry_date.strftime("%Y-%m-%d %H:%M UTC")
        await message.answer(
            f"ℹ️ <b>Already Premium</b>\n\n"
            f"User <code>{user_id}</code> is already a premium user.\n"
            f"<b>Current expiry:</b> {expiry}\n\n"
            f"💡 Use <code>/extendlimit {user_id} &lt;days&gt;</code> to extend their subscription."
        )
        return
    
    # Upgrade the user
    success = await user_queries.upgrade_user_to_premium(db_pool, user_id)
    if success:
        await message.answer(
            f"✅ <b>Upgrade Successful!</b>\n\n"
            f"User <code>{user_id}</code> has been upgraded to 💎 Premium.\n\n"
            f"<b>New Benefits:</b>\n"
            f"• 100 daily AI queries\n"
            f"• 50 daily PDF downloads\n"
            f"• Access to all locked PDFs\n"
            f"• Valid for 30 days\n\n"
            f"✉️ Sending notification to user..."
        )
        
        # Notify the user
        try:
            await bot.send_message(
                user_id,
                "🎉 <b>Congratulations!</b> 🎉\n\n"
                "Your premium subscription has been <b>activated</b>!\n\n"
                "💎 <b>You are now a Premium User for 30 days</b>\n\n"
                "<b>Your Premium Benefits:</b>\n"
                "✅ 100 AI queries per day (resets daily)\n"
                "✅ 50 PDF downloads per day (resets daily)\n"
                "✅ All locked PDFs are now unlocked 🔓\n"
                "✅ Priority support\n\n"
                "Use /stats to check your subscription details.\n\n"
                "Thank you for upgrading! 🙏"
            )
            await message.answer("✅ User has been notified successfully.")
        except Exception as e:
            await message.answer(
                f"⚠️ <b>Upgrade successful, but notification failed:</b>\n"
                f"<code>{str(e)}</code>\n\n"
                f"The user may have blocked the bot or deleted their account."
            )
    else:
        await message.answer(
            f"❌ <b>Database Error</b>\n\n"
            f"Failed to upgrade user <code>{user_id}</code>. Check logs for details."
        )

@router.message(Command(commands=["endplan"]))
async def admin_end_plan(message: Message, bot: Bot, db_pool):
    """End a user's premium subscription"""
    command, arg = parse_command(message.text)
    
    # FIXED: Proper validation
    if not arg:
        await message.answer(
            "❌ <b>Invalid Usage</b>\n\n"
            "<b>Usage:</b> <code>/endplan &lt;user_id&gt;</code>\n\n"
            "<b>Example:</b> <code>/endplan 123456789</code>\n\n"
            "⚠️ <i>This will immediately downgrade the user to free tier.</i>"
        )
        return
    
    if not arg.isdigit():
        await message.answer(
            f"❌ <b>Invalid User ID</b>\n\n"
            f"'{arg}' is not a valid user ID. User IDs must be numbers only."
        )
        return

    user_id = int(arg)
    
    # Check if user exists and is premium
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer(f"❌ User <code>{user_id}</code> does not exist in database.")
        return
    
    if not user.is_premium:
        await message.answer(
            f"ℹ️ User <code>{user_id}</code> is already on the free tier.\n"
            f"No action needed."
        )
        return
    
    # End the plan
    success = await user_queries.end_user_plan(db_pool, user_id)
    if success:
        await message.answer(
            f"✅ <b>Plan Ended</b>\n\n"
            f"User <code>{user_id}</code> has been downgraded to free tier.\n\n"
            f"<b>New Limits:</b>\n"
            f"• 10 AI queries per day\n"
            f"• 10 PDF downloads per 30 days\n"
            f"• Locked PDFs are now restricted\n\n"
            f"✉️ Sending notification..."
        )
        
        # Notify user
        try:
            await bot.send_message(
                user_id,
                "📢 <b>Premium Subscription Ended</b>\n\n"
                "Your premium plan has been terminated by an administrator.\n\n"
                "You have been moved back to the <b>Free Tier</b>.\n\n"
                "<b>Current Limits:</b>\n"
                "• 10 AI queries per day\n"
                "• 10 PDF downloads per 30 days\n\n"
                "Use /upgrade to renew your premium subscription."
            )
        except Exception as e:
            logging.warning(f"Could not notify user {user_id}: {e}")
    else:
        await message.answer(f"❌ Failed to end plan for user <code>{user_id}</code>.")

@router.message(Command(commands=["extendlimit"]))
async def admin_extend_limit(message: Message, db_pool):
    """Extend a premium user's subscription"""
    command, arg_string = parse_command(message.text)
    
    # FIXED: Better validation and error messages
    if not arg_string:
        await message.answer(
            "❌ <b>Invalid Usage</b>\n\n"
            "<b>Usage:</b> <code>/extendlimit &lt;user_id&gt; &lt;days&gt;</code>\n\n"
            "<b>Example:</b> <code>/extendlimit 123456789 30</code>\n\n"
            "💡 This adds extra days to an existing premium subscription."
        )
        return
    
    try:
        parts = arg_string.split()
        if len(parts) != 2:
            raise ValueError("Need exactly 2 arguments")
        
        user_id_str, days_str = parts
        user_id = int(user_id_str)
        days = int(days_str)
        
        if days <= 0:
            await message.answer(
                "❌ <b>Invalid Days Value</b>\n\n"
                "Days must be a positive number greater than 0."
            )
            return
        
        if days > 365:
            await message.answer(
                "❌ <b>Days Too High</b>\n\n"
                "Maximum extension is 365 days. Use a smaller number."
            )
            return
            
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Format</b>\n\n"
            "<b>Usage:</b> <code>/extendlimit &lt;user_id&gt; &lt;days&gt;</code>\n\n"
            "Both user_id and days must be valid numbers.\n\n"
            "<b>Example:</b> <code>/extendlimit 123456789 30</code>"
        )
        return
    
    # Check if user exists and is premium
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer(f"❌ User <code>{user_id}</code> does not exist.")
        return
    
    if not user.is_premium:
        await message.answer(
            f"❌ <b>User Not Premium</b>\n\n"
            f"User <code>{user_id}</code> is not a premium user.\n\n"
            f"💡 Use <code>/upgradeuser {user_id}</code> first to make them premium."
        )
        return
    
    # Extend the subscription
    success = await user_queries.extend_user_premium(db_pool, user_id, days)
    if success:
        # Get updated user info
        updated_user = await user_queries.get_user(db_pool, user_id)
        new_expiry = updated_user.premium_expiry_date.strftime("%Y-%m-%d %H:%M UTC")
        
        await message.answer(
            f"✅ <b>Subscription Extended!</b>\n\n"
            f"User <code>{user_id}</code>'s premium plan extended by <b>{days} days</b>.\n\n"
            f"<b>New Expiry Date:</b> {new_expiry}"
        )
    else:
        await message.answer(
            f"❌ Failed to extend subscription for user <code>{user_id}</code>."
        )

# --- Admin: Stats ---

@router.message(Command(commands=["stats"]))
async def admin_stats(message: Message, db_pool):
    """Get bot statistics"""
    stats = await user_queries.get_bot_stats(db_pool)
    
    # Calculate percentage
    premium_percentage = (stats.total_premium / stats.total_users * 100) if stats.total_users > 0 else 0
    active_percentage = (stats.active_today / stats.total_users * 100) if stats.total_users > 0 else 0
    
    stats_text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 <b>Total Users:</b> {stats.total_users:,}\n"
        f"💎 <b>Premium Users:</b> {stats.total_premium:,} ({premium_percentage:.1f}%)\n"
        f"👤 <b>Free Users:</b> {stats.total_users - stats.total_premium:,}\n\n"
        f"✅ <b>Active Today:</b> {stats.active_today:,} ({active_percentage:.1f}%)\n"
        f"💤 <b>Inactive Today:</b> {stats.total_users - stats.active_today:,}\n\n"
        f"📅 <b>Report Generated:</b> {message.date.strftime('%Y-%m-%d %H:%M UTC')}"
    )
    await message.answer(stats_text)

# --- Admin: Delete PDF (ENHANCED) ---

@router.message(Command(commands=["deletepdf"]))
async def admin_delete_pdf(message: Message, db_pool):
    """Search and delete PDFs"""
    command, query = parse_command(message.text)
    
    if not query:
        await message.answer(
            "❌ <b>Invalid Usage</b>\n\n"
            "<b>Usage:</b> <code>/deletepdf &lt;search term&gt;</code>\n\n"
            "<b>Example:</b> <code>/deletepdf physics chapter 1</code>\n\n"
            "I will search for PDFs matching your term and let you select which to delete."
        )
        return

    await message.answer(f"🔍 Searching for PDFs with '<b>{query}</b>'...")
    
    pdf_results = await pdf_queries.admin_search_pdfs_by_title(db_pool, query)
    
    if not pdf_results:
        await message.answer(
            f"❌ <b>No Results Found</b>\n\n"
            f"I couldn't find any PDFs matching '<b>{query}</b>'.\n\n"
            "💡 Try:\n"
            "• Using fewer words\n"
            "• Checking for typos\n"
            "• Using more general terms"
        )
        return
    
    if len(pdf_results) > 20:
        await message.answer(
            f"⚠️ <b>Too Many Results</b>\n\n"
            f"Found <b>{len(pdf_results)}</b> PDFs matching your search.\n\n"
            "Please be more specific to narrow down the results."
        )
        return

    await message.answer(
        f"✅ Found <b>{len(pdf_results)}</b> match(es) for '<b>{query}</b>'.\n\n"
        "Select the PDF you want to delete:",
        reply_markup=inline_keyboards.get_pdf_deletion_keyboard(pdf_results)
    )

@router.callback_query(F.data.startswith("del_select:"))
async def admin_select_pdf_to_delete(callback: CallbackQuery, state: FSMContext):
    """Handle PDF selection for deletion"""
    pdf_id = int(callback.data.split(":")[1])
    
    # Get the PDF title from the button text
    pdf_title = ""
    for button_row in callback.message.reply_markup.inline_keyboard:
        for button in button_row:
            if button.callback_data == callback.data:
                # Extract title from button text (remove "ID: XXX | " prefix)
                pdf_title = button.text.split(" | ", 1)[1] if " | " in button.text else button.text
                break
    
    await state.set_state(AdminFlow.DeletePDF_AwaitingConfirmation)
    await state.update_data(pdf_id=pdf_id, pdf_title=pdf_title)
    
    await callback.message.edit_text(
        f"⚠️ <b>Confirm Deletion</b>\n\n"
        f"Are you sure you want to permanently delete this PDF?\n\n"
        f"<b>Title:</b> {pdf_title}\n"
        f"<b>ID:</b> <code>{pdf_id}</code>\n\n"
        f"<b>⚠️ This action cannot be undone!</b>",
        reply_markup=inline_keyboards.get_delete_confirmation_keyboard(pdf_id)
    )
    await callback.answer()

@router.callback_query(AdminFlow.DeletePDF_AwaitingConfirmation, F.data.startswith("del_confirm:"))
async def admin_confirm_delete(callback: CallbackQuery, state: FSMContext, db_pool):
    """Confirm and execute PDF deletion"""
    pdf_id = int(callback.data.split(":")[1])
    
    data = await state.get_data()
    pdf_title = data.get('pdf_title', f"ID: {pdf_id}")
    
    success = await pdf_queries.delete_pdf_by_id(db_pool, pdf_id)
    
    if success:
        await callback.message.edit_text(
            f"✅ <b>Successfully Deleted</b>\n\n"
            f"<b>Title:</b> {pdf_title}\n"
            f"<b>ID:</b> <code>{pdf_id}</code>\n\n"
            f"The PDF has been permanently removed from the database."
        )
        logging.info(f"Admin deleted PDF {pdf_id}: {pdf_title}")
    else:
        await callback.message.edit_text(
            f"❌ <b>Deletion Failed</b>\n\n"
            f"Could not delete PDF <code>{pdf_id}</code>.\n\n"
            f"The PDF may have already been deleted or a database error occurred."
        )
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "del_cancel")
async def admin_cancel_delete(callback: CallbackQuery, state: FSMContext):
    """Cancel PDF deletion"""
    if await state.get_state() is not None:
        await state.clear()
    
    await callback.message.edit_text(
        "❌ <b>Deletion Cancelled</b>\n\n"
        "No changes were made to the database."
    )
    await callback.answer("Cancelled")

# --- Admin: Broadcast (ENHANCED PLACEHOLDER) ---

@router.message(Command(commands=["broadcast"]))
async def admin_broadcast(message: Message, state: FSMContext):
    """Initiate broadcast to all users"""
    command, arg = parse_command(message.text)
    
    if arg:
        await message.answer(
            "❌ <b>Invalid Usage</b>\n\n"
            "Direct broadcast messages are not yet implemented.\n\n"
            "<b>Usage:</b> <code>/broadcast</code> (no arguments)\n\n"
            "I will then ask you for the message to broadcast."
        )
        return
    
    await state.set_state(AdminFlow.AwaitingBroadcastMessage)
    await message.answer(
        "📢 <b>Broadcast Mode</b>\n\n"
        "Send me the message you want to broadcast to all users.\n\n"
        "You can send:\n"
        "• Text message\n"
        "• Photo with caption\n"
        "• Document\n\n"
        "Type /stop to cancel."
    )

@router.message(AdminFlow.AwaitingBroadcastMessage)
async def broadcast_message_received(message: Message, state: FSMContext, db_pool, bot: Bot):
    """Handle broadcast message and send to all users"""
    await state.clear()
    
    # Get all user IDs
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")
    
    if not users:
        await message.answer("❌ No users found in database.")
        return
    
    total_users = len(users)
    success_count = 0
    failed_count = 0
    blocked_count = 0
    
    status_msg = await message.answer(
        f"📤 <b>Broadcasting...</b>\n\n"
        f"Total users: {total_users}\n"
        f"Progress: 0/{total_users}"
    )
    
    # Broadcast to all users
    for idx, user_row in enumerate(users):
        user_id = user_row['user_id']
        
        try:
            if message.photo:
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
            elif message.document:
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
            else:
                await bot.send_message(user_id, message.text or message.caption)
            
            success_count += 1
            
        except Exception as e:
            error_str = str(e).lower()
            if "blocked" in error_str or "forbidden" in error_str:
                blocked_count += 1
            else:
                failed_count += 1
            logging.warning(f"Failed to send broadcast to {user_id}: {e}")
        
        # Update status every 50 users
        if (idx + 1) % 50 == 0:
            try:
                await status_msg.edit_text(
                    f"📤 <b>Broadcasting...</b>\n\n"
                    f"Progress: {idx + 1}/{total_users}\n"
                    f"✅ Sent: {success_count}\n"
                    f"❌ Failed: {failed_count}\n"
                    f"🚫 Blocked: {blocked_count}"
                )
            except:
                pass
    
    # Final report
    await status_msg.edit_text(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"📊 <b>Results:</b>\n"
        f"• Total Users: {total_users}\n"
        f"• ✅ Successfully Sent: {success_count}\n"
        f"• ❌ Failed: {failed_count}\n"
        f"• 🚫 Blocked Bot: {blocked_count}\n\n"
        f"Success Rate: {(success_count/total_users*100):.1f}%"
    )
    
    logging.info(f"Broadcast complete: {success_count}/{total_users} successful")