import asyncpg
import logging
from typing import Optional
from dataclasses import dataclass
import datetime

# Using a dataclass is a clean way to pass user data around
@dataclass
class User:
    user_id: int
    username: Optional[str]
    selected_class: str
    is_premium: bool
    premium_expiry_date: Optional[any] # Will be a datetime object
    ai_limit_remaining: int
    pdf_downloads_remaining: int
    pdf_downloads_reset_date: Optional[any] # Will be a datetime object
    first_seen: Optional[any]               # <-- YOU WERE MISSING THIS
    last_active: Optional[any]
async def get_user(pool: asyncpg.Pool, user_id: int) -> Optional[User]:
    """
    Fetches a user from the database by their user_id.
    Returns a User object or None if not found.
    """
    async with pool.acquire() as conn:
        # fetchrow() gets one record or None
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        
        # Convert the database row (which is a dict-like object)
        # into our clean 'User' dataclass
        if row:
            return User(**dict(row))
        return None

async def create_user(pool: asyncpg.Pool, user_id: int, username: Optional[str]) -> User:
    """
    Creates a new user in the database with default values.
    If the user already exists, it fetches them.
    Returns the User object.
    """
    async with pool.acquire() as conn:
        try:
            # 'ON CONFLICT (user_id) DO NOTHING' is a safety check.
            # If the user somehow already exists, it won't crash.
            await conn.execute(
                """
                INSERT INTO users (user_id, username, last_active)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id, username
            )
            logging.info(f"Created new user with ID: {user_id}")
            
            # Fetch the user we just created (or the existing one)
            return await get_user(pool, user_id)
            
        except Exception as e:
            logging.error(f"Error creating/fetching user {user_id}: {e}")
            return None

async def set_user_class(pool: asyncpg.Pool, user_id: int, selected_class: str) -> bool:
    """
    Updates a user's selected_class in the database.
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "UPDATE users SET selected_class = $1, last_active = CURRENT_TIMESTAMP WHERE user_id = $2",
                selected_class, user_id
            )
            logging.info(f"Set class for user {user_id} to {selected_class}")
            return True
        except Exception as e:
            logging.error(f"Error setting class for user {user_id}: {e}")
            return False

async def update_user_last_active(pool: asyncpg.Pool, user_id: int):
    """
    Updates the 'last_active' timestamp for a user.
    We will call this on almost every message.
    """
    async with pool.acquire() as conn:
        try:
            # This is a "fire-and-forget" query; we don't need a result
            await conn.execute(
                "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = $1",
                user_id
            )
        except Exception as e:
            # We log this as a warning because it's not critical
            logging.warning(f"Could not update last_active for {user_id}: {e}")
            # ADD THIS TO: bot/db/user_queries.py
async def decrement_pdf_download_limit(pool: asyncpg.Pool, user_id: int) -> bool:
    """
    Decrements a user's total PDF download limit.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE users
            SET pdf_downloads_remaining = pdf_downloads_remaining - 1,
                last_active = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND pdf_downloads_remaining > 0
            """,
            user_id
        )
        if result == "UPDATE 1":
            return True
        return False

async def decrement_ai_limit(pool: asyncpg.Pool, user_id: int) -> bool:
    """
    Decrements a user's AI limit. Returns True if successful, False if at 0.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE users
            SET ai_limit_remaining = ai_limit_remaining - 1,
                last_active = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND ai_limit_remaining > 0
            """,
            user_id
        )
        if result == "UPDATE 1":
            return True
        return False
    # (Add these functions at the end of the file)
# --- ADMIN: Premium Management ---

async def upgrade_user_to_premium(pool: asyncpg.Pool, user_id: int, days: int = 30) -> bool:
    """
    Upgrades a user to premium for a number of days.
    Resets their limits to the premium tier.
    """
    # Calculate the new expiry date
    expiry_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
    
    async with pool.acquire() as conn:
        try:
            # We set premium, set the expiry date, and reset limits all at once
            await conn.execute(
                """
                UPDATE users
                SET
                    is_premium = TRUE,
                    premium_expiry_date = $1,
                    ai_limit_remaining = 100,  -- Premium AI limit
                    pdf_downloads_remaining = 50,  -- Premium PDF limit
                    pdf_downloads_reset_date = NULL
                WHERE user_id = $2
                """,
                expiry_date, user_id
            )
            logging.info(f"Upgraded user {user_id} to premium for {days} days.")
            return True
        except Exception as e:
            logging.error(f"Error upgrading user {user_id}: {e}")
            return False

async def extend_user_premium(pool: asyncpg.Pool, user_id: int, days_to_add: int) -> bool:
    """
    Adds more days to a user's *existing* premium plan.
    """
    async with pool.acquire() as conn:
        try:
            # This SQL command finds the current expiry date and adds days to it
            await conn.execute(
                """
                UPDATE users
                SET premium_expiry_date = premium_expiry_date + ($1::INTERVAL)
                WHERE user_id = $2 AND is_premium = TRUE
                """,
                datetime.timedelta(days=days_to_add), user_id
            )
            logging.info(f"Extended premium for user {user_id} by {days_to_add} days.")
            return True
        except Exception as e:
            logging.error(f"Error extending premium for {user_id}: {e}")
            return False

async def end_user_plan(pool: asyncpg.Pool, user_id: int) -> bool:
    """
    Ends a user's premium plan and resets them to free tier.
    """
    async with pool.acquire() as conn:
        try:
            # We set premium to false, clear the expiry date, and reset limits
            await conn.execute(
                """
                UPDATE users
                SET
                    is_premium = FALSE,
                    premium_expiry_date = NULL,
                    ai_limit_remaining = 10,           -- Free AI limit
                    pdf_downloads_remaining = 10,      -- Free PDF limit
                    pdf_downloads_reset_date = (CURRENT_TIMESTAMP + INTERVAL '30 days')
                WHERE user_id = $1::bigint
                """,
                int(user_id)
            )
            logging.info(f"Ended premium plan for user {user_id}.")
            return True
        except Exception as e:
            logging.error(f"Error ending plan for user {user_id}: {e}")
            return False

# --- ADMIN: Statistics ---

@dataclass
class BotStats:
    total_users: int
    total_premium: int
    active_today: int

async def get_bot_stats(pool: asyncpg.Pool) -> BotStats:
    """
    Fetches bot statistics for the admin.
    """
    # Define "today" as the start of the current day in UTC
    today_start = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    async with pool.acquire() as conn:
        try:
            # We run three separate queries. This is fast and easy to read.
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_premium = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium = TRUE")
            active_today = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE last_active >= $1",
                today_start
            )
            
            return BotStats(
                total_users=total_users,
                total_premium=total_premium,
                active_today=active_today
            )
        except Exception as e:
            logging.error(f"Error getting bot stats: {e}")
            return BotStats(0, 0, 0)
        # (Add these functions at the end of the file)
from typing import List

# --- SCHEDULER: Daily Tasks ---
async def reset_daily_limits(pool: asyncpg.Pool) -> bool:
    """
    Resets ONLY the AI limits for all users.
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute("""
            UPDATE users
            SET
                ai_limit_remaining = CASE
                    WHEN is_premium = TRUE THEN 100
                    ELSE 10
                END;
            """)
            logging.info("SCHEDULER: Successfully reset daily AI limits for all users.")
            return True
        except Exception as e:
            logging.error(f"SCHEDULER: Error resetting daily AI limits: {e}")
            return False
async def get_expired_premium_users(pool: asyncpg.Pool) -> List[int]:
    """
    Finds all users whose premium plan has expired.
    Returns a list of their user_ids.
    """
    async with pool.acquire() as conn:
        try:
            # Find all users who are premium AND whose expiry date is in the past
            # 'CURRENT_TIMESTAMP' is the current time in UTC
            expired_users = await conn.fetch(
                """
                SELECT user_id FROM users
                WHERE
                    is_premium = TRUE AND
                    premium_expiry_date IS NOT NULL AND
                    premium_expiry_date < CURRENT_TIMESTAMP;
                """
            )
            
            # Return a simple list of IDs
            return [row['user_id'] for row in expired_users]
            
        except Exception as e:
            logging.error(f"SCHEDULER: Error finding expired users: {e}")
            return []
        # (Add these at the end of the file)

async def get_expired_free_users(pool: asyncpg.Pool) -> List[int]:
    """
    Finds all free users whose 30-day PDF limit cycle has expired.
    Returns a list of their user_ids.
    """
    async with pool.acquire() as conn:
        try:
            expired_users = await conn.fetch(
                """
                SELECT user_id FROM users
                WHERE
                    is_premium = FALSE AND
                    pdf_downloads_reset_date IS NOT NULL AND
                    pdf_downloads_reset_date < CURRENT_TIMESTAMP;
                """
            )
            return [row['user_id'] for row in expired_users]
        except Exception as e:
            logging.error(f"SCHEDULER: Error finding expired free users: {e}")
            return []

async def reset_free_user_pdf_downloads(pool: asyncpg.Pool, user_id: int) -> bool:
    """
    Resets a free user's PDF downloads back to 10
    and sets their next reset date to 30 days from now.
    """
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                UPDATE users
                SET
                    pdf_downloads_remaining = 10,
                    pdf_downloads_reset_date = (CURRENT_TIMESTAMP + INTERVAL '30 days')
                WHERE user_id = $1 AND is_premium = FALSE;
                """,
                user_id
            )
            return True
        except Exception as e:
            logging.error(f"SCHEDULER: Error resetting PDF downloads for free user {user_id}: {e}")
            return False