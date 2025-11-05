"""
Handler Registration Module - FIXED VERSION

CRITICAL: ORDER MATTERS!
Handlers are checked in the order they're registered.

Priority (from highest to lowest):
1. Stop/Menu commands (MUST be first - work from any state)
2. User start/registration (for /start command)
3. Admin commands (high priority for admin functions)
4. Payment flow (must come before FSM states)
5. FSM state-specific handlers (PDF search, AI chat)
6. General commands and text handlers (lowest priority, catch-all)
"""

from aiogram import Router
import logging

# Import stop/menu handler FIRST
from . import user_stop_menu  # NEW: Separate stop/menu handler

# Import all other handler routers
from . import user_start
from . import admin
from . import payment
from . import ai_chat
from . import pdf_search
from . import unknown_text

# Create the main router that combines all other routers
all_handlers_router = Router()

# ============================================================================
# CRITICAL: REGISTRATION ORDER (DO NOT CHANGE WITHOUT UNDERSTANDING!)
# ============================================================================

# --- 1. STOP/MENU COMMANDS (HIGHEST PRIORITY) ---
# These MUST work from ANY state, so they come first
# /stop, /menu, /help, /stats
all_handlers_router.include_router(user_stop_menu.router)
logging.info("✅ Registered: Stop/Menu handlers (Priority 1)")

# --- 2. USER START & REGISTRATION ---
# Must be early to handle /start, /changeclass, and user onboarding
# These are the entry points and should never be blocked
all_handlers_router.include_router(user_start.router)
logging.info("✅ Registered: User start handlers (Priority 2)")

# --- 3. ADMIN COMMANDS ---
# Admin commands must come before general handlers to avoid conflicts
# Admin commands are filtered by AdminFilter, so they won't interfere with users
all_handlers_router.include_router(admin.router)
logging.info("✅ Registered: Admin handlers (Priority 3)")

# --- 4. PAYMENT FLOW ---
# Payment must come before FSM states to handle callbacks properly
all_handlers_router.include_router(payment.router)
logging.info("✅ Registered: Payment handlers (Priority 4)")

# --- 5. AI CHAT (FSM STATE) ---
# AI Chat: Handles AI conversation and message history
# Must come before general text handlers
all_handlers_router.include_router(ai_chat.router)
logging.info("✅ Registered: AI chat handlers (Priority 5)")

# --- 6. PDF SEARCH (FSM STATE) ---
# PDF Search: Handles search flow and results
# Must come before general text handlers
all_handlers_router.include_router(pdf_search.router)
logging.info("✅ Registered: PDF search handlers (Priority 6)")

# --- 7. GENERAL USER HANDLERS ---
# General commands and responses (lower priority)

# --- 8. UNKNOWN TEXT (LOWEST PRIORITY) ---
# Catch-all for unrecognized text (must be last)
all_handlers_router.include_router(unknown_text.router)
logging.info("✅ Registered: Unknown text handler (Priority 8 - Last)")

# ============================================================================
# DEBUGGING: Log router registration
# ============================================================================
logging.info("=" * 80)
logging.info("✅ ALL HANDLERS REGISTERED SUCCESSFULLY")
logging.info("=" * 80)
logging.info("Handler priority order:")
logging.info("  1. Stop/Menu (works from any state)")
logging.info("  2. User Start (/start, /changeclass)")
logging.info("  3. Admin (admin-only commands)")
logging.info("  4. Payment (/upgrade, payment flow)")
logging.info("  5. AI Chat (FSM state handlers)")
logging.info("  6. PDF Search (FSM state handlers)")
logging.info("  7. Unknown Text (catch-all)")
logging.info("=" * 80)

# ============================================================================
# NOTES FOR DEVELOPERS
# ============================================================================
"""
KEY FIXES IN THIS VERSION:

1. ✅ SEPARATE STOP/MENU HANDLER
   - Created dedicated user_stop_menu.py
   - /stop now works from ANY state
   - /menu shows main menu
   - /help and /stats are separate

2. ✅ STATE FILTERS EVERYWHERE
   - All handlers now use proper StateFilter
   - AI chat: Only in AwaitingAIPrompt state
   - PDF search: Only in AwaitingSearchQuery state
   - Commands block FSM states properly

3. ✅ REDIS ERROR HANDLING
   - AI cache errors are non-fatal
   - Bot continues even if Redis fails
   - Proper logging of cache failures

4. ✅ COMMAND BLOCKING IN FSM STATES
   - PDF search won't accept /help anymore
   - Commands like /help blocked during active operations
   - Use /stop to exit any operation

5. ✅ QR CODE FIXED
   - Payment handler sends QR directly to user
   - Proper error handling if QR fails
   - Better logging of payment flow

6. ✅ AI MODEL INITIALIZATION
   - Better error handling
   - Retry logic on failures
   - Fallback to older model if needed

TESTING CHECKLIST:
□ /start works for new users
□ /start works for existing users  
□ /stop works from ANY state (AI, PDF search, payment)
□ /menu shows main menu when not in FSM state
□ /help works and shows all commands
□ /stats shows user statistics
□ /changeclass allows class selection
□ /search starts PDF search flow
□ PDF search BLOCKS commands like /help
□ PDF search returns results
□ PDF download works for free/premium users
□ AI chat button starts conversation
□ AI chat BLOCKS commands like /help
□ AI chat remembers context
□ AI cache works (check logs for HIT/MISS)
□ /upgrade shows payment info
□ Payment QR code is sent successfully
□ Payment screenshot upload works
□ Admin commands work (if admin)
□ General text responses work when not in FSM state
□ /stop cancels any active operation

COMMON ISSUES FIXED:
- ❌ "/help accepted during PDF search" → ✅ Now blocked
- ❌ "AI cache errors crash bot" → ✅ Now non-fatal
- ❌ "QR code not sending" → ✅ Fixed send_photo call
- ❌ "Don't know which function I'm in" → ✅ StateFilter everywhere
- ❌ "404 AI errors" → ✅ Better model initialization
- ❌ "/stop not working" → ✅ Highest priority, no state filter
"""