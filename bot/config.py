import os
import logging
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv()

# --- Bot and Admin ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.critical("BOT_TOKEN is not set in the .env file")
    raise ValueError("BOT_TOKEN is not set in the .env file")

ADMIN_ID_STR = os.getenv("ADMIN_ID")
if not ADMIN_ID_STR:
    logging.critical("ADMIN_ID is not set in the .env file")
    raise ValueError("ADMIN_ID is not set in the .env file")

try:
    ADMIN_ID = int(ADMIN_ID_STR)
except ValueError:
    logging.critical(f"ADMIN_ID '{ADMIN_ID_STR}' is not a valid integer")
    raise ValueError("ADMIN_ID must be an integer")
    
CHANNEL_ID = os.getenv("CHANNEL_ID")
if not CHANNEL_ID:
    logging.critical("CHANNEL_ID is not set in the .env file (e.g., @mychannel)")
    raise ValueError("CHANNEL_ID is not set in the .env file")

#
# (in bot/config.py)

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logging.critical("DATABASE_URL is not set! You must provide the full PostgreSQL URL")
    raise ValueError("DATABASE_URL must be set in format: postgresql://user:pass@host:port/dbname")

# --- Redis Configuration ---
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    logging.critical("REDIS_URL is not set! You must provide the full Redis URL")
    raise ValueError("REDIS_URL must be set in format: redis://user:pass@host:port/0")

# Use a different database number for AI cache
try:
    base_redis_url = REDIS_URL.rsplit('/', 1)[0]
    AI_CACHE_REDIS_URL = f"{base_redis_url}/1"
    logging.info("AI cache Redis URL configured successfully")
except Exception as e:
    logging.critical(f"Failed to configure AI cache Redis URL: {e}")
    raise ValueError("Invalid REDIS_URL format")

# --- Webhook Configuration ---
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL", "https://finaltarsbot-production.up.railway.app")
if not BASE_WEBHOOK_URL:
    logging.critical("BASE_WEBHOOK_URL is not set! You must provide the base URL for webhooks")
    raise ValueError("BASE_WEBHOOK_URL must be set (e.g., https://your-domain.com)")

# --- AI CONFIG ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY is not set. The AI feature will not work.")