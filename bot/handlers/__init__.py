from aiogram import Router
from aiogram.types import Message

# Import all your handler routers
from . import user_start
from . import user_general
from . import admin
from . import pdf_search
from . import ai_chat
from . import payment
from . import user_stop
# This is the main router that combines all other routers
all_handlers_router = Router()

# --- ORDER IS CRITICAL ---
# 1. Admin commands (highest priority)
all_handlers_router.include_router(user_start.router)
all_handlers_router.include_router(admin.router)

# 2. hh

# 3. Specific text button handlers
all_handlers_router.include_router(pdf_search.router)
all_handlers_router.include_router(ai_chat.router)
all_handlers_router.include_router(payment.router)

# 4. General text handlers (MUST BE AFTER BUTTONS)
all_handlers_router.include_router(user_general.router)
all_handlers_router.include_router(user_stop.router)

# 5. Final fallback for any message not caughtgit
