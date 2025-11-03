import asyncio
import logging
import asyncpg
from aiogram import Bot

# We need to import our config and DB functions
from bot.config import DATABASE_URL, BOT_TOKEN
from bot.db import user_queries

# Set up logging for this script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - SCHEDULER - %(message)s",
)

async def run_daily_tasks():
    """
    The main function for the daily scheduled tasks.
    """
    logging.info("Starting daily scheduler tasks...")
    
    db_pool = None
    bot = None
    
    try:
        # --- 1. Connect to Database ---
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        if db_pool:
            logging.info("Successfully connected to database.")
        else:
            logging.error("Failed to create database pool.")
            return
            
        # --- 2. Connect to Bot (to send messages) ---
        bot = Bot(token=BOT_TOKEN)

        # --- 3. Process Expired Subscriptions ---
        logging.info("Checking for expired premium users...")
        expired_user_ids = await user_queries.get_expired_premium_users(db_pool)
        
        if not expired_user_ids:
            logging.info("No expired users found.")
        else:
            logging.info(f"Found {len(expired_user_ids)} expired users. Downgrading...")
            for user_id in expired_user_ids:
                success = await user_queries.end_user_plan(db_pool, user_id)
                if success:
                    logging.info(f"Downgraded user {user_id}.")
                    # Try to notify the user
                    try:
                        await bot.send_message(
                            user_id,
                            "Your 💎 Premium Plan has expired. "
                            "You have been returned to the free tier.\n\n"
                            "Use /upgrade to renew!"
                        )
                    except Exception as e:
                        logging.warning(f"Could not notify user {user_id} of expiry: {e}")
                else:
                    logging.error(f"Failed to downgrade user {user_id}.")

        # --- 4. Process Expired Free User PDF Downloads ---
        logging.info("Checking for free users needing PDF downloads reset...")
        free_user_ids = await user_queries.get_expired_free_users(db_pool)
        
        if not free_user_ids:
            logging.info("No free users need a PDF downloads reset.")
        else:
            logging.info(f"Found {len(free_user_ids)} free users. Resetting their PDF downloads...")
            for user_id in free_user_ids:
                if await user_queries.reset_free_user_pdf_downloads(db_pool, user_id):
                    logging.info(f"Reset PDF downloads for free user {user_id}.")
                else:
                    logging.error(f"Failed to reset PDF downloads for free user {user_id}.")

        # --- 5. Reset Daily AI Limits ---
        logging.info("Resetting daily AI limits for all users...")
        if await user_queries.reset_daily_limits(db_pool):
            logging.info("Successfully reset all daily limits.")
        else:
            logging.error("Failed to reset daily limits.")

    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}")
        
    finally:
        # --- 6. Clean Up ---
        if db_pool:
            await db_pool.close()
            logging.info("Database connection closed.")
        if bot:
            await bot.session.close()
            logging.info("Bot session closed.")
            
    logging.info("Daily scheduler tasks finished.")

# --- How to run this file ---
# You don't run this with the main bot.
# You set up a 'cron job' on your server to run this
# command once per day (e.g., at midnight):
#
# /path/to/your/venv/bin/python -m bot.utils.scheduler
#
if __name__ == "__main__":
    asyncio.run(run_daily_tasks())