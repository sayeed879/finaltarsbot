import asyncio
import logging
import os
import redis.asyncio as aioredis
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import setup_application

# --- Import all Configs and Handlers ---
from bot.config import (
    BOT_TOKEN,
    REDIS_URL,
    AI_CACHE_REDIS_URL,
    DATABASE_URL,
    BASE_WEBHOOK_URL,
    ADMIN_ID
)
from bot.db.db_setup import create_db_pool, close_db_pool
from bot.handlers import all_handlers_router
from bot.middleware.activity import UserActivityMiddleware


# --- Webhook Configuration ---
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_SECRET = "TarsBotWebhookSecret2025"
WEBHOOK_URL = f"{BASE_WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"


# --- Startup Function ---
async def on_startup(app: web.Application):
    """Called when the aiohttp server starts."""
    logging.info("AIOHTTP server starting up...")

    # 1. Create database and cache connections
    db_pool = await create_db_pool()
    ai_cache_redis = aioredis.from_url(AI_CACHE_REDIS_URL, decode_responses=True)

    # 2. Get bot and dispatcher from app
    bot: Bot = app["bot"]
    dp: Dispatcher = app["dp"]

    # 3. Store connections in dispatcher for access
    dp["db_pool"] = db_pool
    dp["ai_cache"] = ai_cache_redis

    # 4. Set webhook with Telegram
    try:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET
        )
        logging.info(f"✅ Webhook set to: {WEBHOOK_URL}")
    except Exception as e:
        logging.warning(f"⚠️ Failed to set webhook (OK if another worker did): {e}")


# --- Shutdown Function ---
async def on_shutdown(app: web.Application):
    """Called when the aiohttp server shuts down."""
    logging.info("AIOHTTP server shutting down...")

    bot: Bot = app["bot"]
    dp: Dispatcher = app["dp"]

    # 1. Close connections safely
    if "db_pool" in dp:
        await close_db_pool()
    if "ai_cache" in dp:
        await dp["ai_cache"].close()

    # 2. Delete webhook
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("✅ Webhook deleted successfully.")


# --- Middleware for Logging ---
@web.middleware
async def request_logging_middleware(request, handler):
    """Log all incoming requests and their processing time"""
    start_time = asyncio.get_event_loop().time()
    try:
        response = await handler(request)
        return response
    finally:
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        status = getattr(response, "status", "Failed")
        logging.info(f"{request.method} {request.path} {status} ({duration:.3f}s)")


# --- Health Check (for Railway / Monitoring) ---
async def health_check(request):
    return web.Response(text="OK", status=200)


# --- Create and Configure aiohttp Application ---
def create_app() -> web.Application:
    """Creates and configures the main aiohttp web application."""
    logging.critical("!!!!!!!! EXECUTING LATEST CODE - v2 !!!!!!!!")

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

    # 4. Create aiohttp Web App
    app = web.Application(middlewares=[request_logging_middleware])

    # 5. Attach bot and dispatcher to app
    app["bot"] = bot
    app["dp"] = dp

    # 6. Register startup/shutdown handlers
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # 7. Add health check endpoint
    app.router.add_get("/health", health_check)

    # 8. Setup aiogram webhook route
    setup_application(
        app,
        dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        webhook_path=WEBHOOK_PATH
    )

    logging.info("✅ AIOHTTP application configured successfully.")
    return app


# --- Gunicorn Entry Point ---
app = create_app()
