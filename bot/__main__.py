import asyncio
import logging
import os
import redis.asyncio as aioredis
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
# --- 1. THIS IMPORT IS CHANGED ---
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# --- Import all Configs and Handlers ---
from bot.config import (
    BOT_TOKEN, REDIS_URL, AI_CACHE_REDIS_URL, DATABASE_URL, BASE_WEBHOOK_URL,
    ADMIN_ID
)
from bot.db.db_setup import create_db_pool, close_db_pool
from bot.handlers import all_handlers_router
from bot.middleware.activity import UserActivityMiddleware

# --- Webhook Configuration ---
WEBHOOK_PATH = f"/webhook/{7953333536:AAGZSd7EgJmcOfU8jnpaCqQc9IFq6inGt-c}"
WEBHOOK_SECRET = "TarsBotWebhookSecret2025"  # Safe webhook secret
WEBHOOK_URL = f"{BASE_WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"  # Ensure clean URL

# --- These functions run when the Web App starts/stops ---

async def on_startup(app: web.Application):
    """
    Called when the aiohttp server starts.
    """
    logging.info("AIOHTTP server starting up...")
    
    # 1. Create connections
    db_pool = await create_db_pool()
    ai_cache_redis = aioredis.from_url(AI_CACHE_REDIS_URL, decode_responses=True)
    
    # 2. Get bot and dispatcher from the app
    bot: Bot = app["bot"]
    dp: Dispatcher = app["dp"]
    
    # 3. Share connections with all handlers
    dp["db_pool"] = db_pool
    dp["ai_cache"] = ai_cache_redis
    
    # 4. Set the webhook with Telegram
    try:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET
        )
        logging.info(f"Webhook set to: {WEBHOOK_URL}")
    except Exception as e:
        # This is NORMAL if you have multiple workers
        logging.warning(f"Failed to set webhook (this is OK if another worker succeeded): {e}")

async def on_shutdown(app: web.Application):
    """
    Called when the aiohttp server shuts down.
    """
    logging.info("AIOHTTP server shutting down...")
    
    # 1. Get resources from the app
    bot: Bot = app["bot"]
    dp: Dispatcher = app["dp"]
    
    # 2. Close connections
    if "db_pool" in dp.workflow_data:
        await close_db_pool()
    if "ai_cache" in dp.workflow_data:
        await dp["ai_cache"].close()
        
    # 3. Delete the webhook
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook deleted.")

# --- This is the main function that creates the app ---

@web.middleware
async def request_logging_middleware(request, handler):
    """Log all requests and their processing time"""
    start_time = asyncio.get_event_loop().time()
    try:
        response = await handler(request)
        return response
    finally:
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        logging.info(f"{request.method} {request.path} {response.status if 'response' in locals() else 'Failed'} ({duration:.3f}s)")

async def health_check(request):
    """Health check endpoint for Railway"""
    return web.Response(text='OK', status=200)

def create_app() -> web.Application:
    """
    Creates and configures the main aiohttp web application.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logging.info("Configuring bot (new webhook mode)...")

    # 1. Setup Bot, Storage, and Dispatcher
    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    fsm_storage = RedisStorage.from_url(REDIS_URL)
    dp = Dispatcher(storage=fsm_storage)

    # 2. Register Middleware
    dp.update.outer_middleware(UserActivityMiddleware())
    
    # 3. Register All Handlers
    dp.include_router(all_handlers_router)

    # 4. Create the aiohttp Web App with middleware
    app = web.Application(middlewares=[request_logging_middleware])
    
    # 5. Store bot and dispatcher in the app
    app["bot"] = bot
    app["dp"] = dp

    # 6. Register startup and shutdown handlers
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # 7. Add health check endpoint
    app.router.add_get("/health", health_check)
    
    # 8. Setup webhook handler
    handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    )
    app.router.add_post(WEBHOOK_PATH, handler)
    
    # 8. Mount aiogram to the web app
    setup_application(app, dp, bot=bot)
    
    logging.info("AIOHTTP application configured successfully.")
    return app

# --- This is the entry point Gunicorn will use ---
app = create_app()