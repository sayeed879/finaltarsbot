from aiogram import Router
from aiogram.types import Message

# Import all your handler routers
from . import user_start
from . import user_general
from . import admin
from . import pdf_search
from . import ai_chat
from . import payment

# This is the main router that combines all other routers
all_handlers_router = Router()

all_handlers_router.include_router(user_start.router)
all_handlers_router.include_router(admin.router)
all_handlers_router.include_router(user_general.router)
all_handlers_router.include_router(pdf_search.router)
all_handlers_router.include_router(ai_chat.router)
all_handlers_router.include_router(payment.router)

# Add a "fallback" handler for any text not caught
@all_handlers_router.message()
async def unknown_message(message: Message):
    pass