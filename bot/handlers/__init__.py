"""
Handler Registration Module

This file controls the order in which message handlers are registered.
ORDER MATTERS: Handlers are checked in the order they're registered.

Priority (from highest to lowest):
1. User start/registration (must be first for /start command)
2. Admin commands (high priority for admin functions)
3. FSM state-specific handlers (PDF search, AI chat, payment)
4. General commands and text handlers (lowest priority, catch-all)
"""

from aiogram import Router
from aiogram.types import Message

# Import all handler routers
from . import user_start
from . import admin
from . import pdf_search
from . import ai_chat
from . import payment
from . import user_general
from . import unknown_text
# Create the main router that combines all other routers
all_handlers_router = Router()

# ============================================================================
# CRITICAL: REGISTRATION ORDER
# ============================================================================
# The order below is carefully designed to prevent handler conflicts.
# DO NOT change this order without understanding the implications!

# --- 1. USER START & REGISTRATION (HIGHEST PRIORITY) ---
# Must be first to handle /start, /changeclass, and user onboarding
# These are the entry points and should never be blocked
all_handlers_router.include_router(user_start.router)


all_handlers_router.include_router(user_general.router)
all_handlers_router.include_router(admin.router)
all_handlers_router.include_router(payment.router)


# --- 2. ADMIN COMMANDS (HIGH PRIORITY) ---
# Admin commands must come before general handlers to avoid conflicts
# Admin commands are filtered by AdminFilter, so they won't interfere with users
all_handlers_router.include_router(ai_chat.router)

all_handlers_router.include_router(pdf_search.router)

# AI Chat: Handles AI conversation and message history

all_handlers_router.include_router(unknown_text.router)

# ============================================================================
# DEBUGGING: Log router registration
# ============================================================================
import logging
logging.info("✅ All handlers registered successfully")
logging.info("Handler order: user_start → admin → pdf_search → ai_chat → payment → user_general")

# ============================================================================
# NOTES FOR DEVELOPERS
# ============================================================================
"""
Common Issues and Solutions:

1. PROBLEM: Commands not working
   SOLUTION: Check if a general text handler is catching them first
   FIX: Make sure command filters come before general text handlers

2. PROBLEM: FSM states not working  
   SOLUTION: Check if StateFilter is properly applied
   FIX: Use StateFilter(None) on general handlers, specific states on FSM handlers

3. PROBLEM: Button callbacks not responding
   SOLUTION: Check if callback_query handlers are registered
   FIX: Make sure to include the router that handles those callbacks

4. PROBLEM: Admin commands not working
   SOLUTION: Check AdminFilter and ensure admin router is registered early
   FIX: Place admin router high in the registration order

5. PROBLEM: Handlers conflicting with each other
   SOLUTION: Check registration order and filters
   FIX: More specific handlers should be registered before general ones

Handler Testing Checklist:
□ /start works for new users
□ /start works for existing users  
□ /help shows help message
□ /stats shows user statistics
□ /changeclass allows class selection
□ /search starts PDF search flow
□ PDF search returns results
□ PDF download works for free/premium users
□ AI chat button starts conversation
□ AI chat remembers context
□ /upgrade shows payment info
□ Payment screenshot upload works
□ Admin commands work (if admin)
□ /stop cancels any active operation
□ General text responses work when not in FSM state
"""