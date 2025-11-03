import asyncpg
import logging
from bot.config import DATABASE_URL

# This 'pool' variable will be shared by the whole bot
pool = None

import asyncio

async def create_db_pool():
    """
    Creates the database connection pool with retries.
    This should be called once when the bot starts.
    """
    global pool
    max_retries = 5
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            # Parse the DATABASE_URL to log connection attempt (without password)
            db_parts = DATABASE_URL.split('@')
            safe_url = f"{db_parts[0].split(':')[0]}:***@{db_parts[1]}" if len(db_parts) > 1 else "DATABASE_URL"
            logging.info(f"Attempting database connection ({attempt + 1}/{max_retries}) to {safe_url}")

            # Create the connection pool with proper SSL and timeout settings
            pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,       # Start with fewer connections
                max_size=10,      # Reduced max connections for Railway
                command_timeout=60,  # 1-minute timeout for commands
                timeout=30,       # 30-second connection timeout
                ssl='require'     # Required for Railway PostgreSQL
            )
            
            logging.info("Successfully created database connection pool")
            
            # Test the connection by executing a simple query
            async with pool.acquire() as conn:
                await conn.execute('SELECT 1')
                logging.info("Database connection test successful")
            
            # Create tables after successful connection
            await setup_database_tables(pool)
            return pool

        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
                logging.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logging.critical(f"Failed to create database pool after {max_retries} attempts: {str(e)}")
                raise

async def setup_database_tables(pool: asyncpg.Pool):
    """
    Runs the SQL commands to create all our tables if they don't exist.
    """
    async with pool.acquire() as conn:
        try:
            # --- Create users table ---
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(100),
                selected_class VARCHAR(20) NOT NULL DEFAULT 'none',
                is_premium BOOLEAN NOT NULL DEFAULT FALSE,
                premium_expiry_date TIMESTAMPTZ,
                ai_limit_remaining INT NOT NULL DEFAULT 10,
                pdf_downloads_remaining INT NOT NULL DEFAULT 10,
                first_seen TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            """)
            
            # --- Create pdfs table ---
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS pdfs (
                pdf_id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                drive_link TEXT NOT NULL,
                is_free BOOLEAN NOT NULL DEFAULT FALSE,
                class_tag VARCHAR(20) NOT NULL,
                search_keywords TEXT
            );
            """)
            
            # --- Create ai_prompts table ---
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_prompts (
                prompt_id SERIAL PRIMARY KEY,
                class_tag VARCHAR(20) NOT NULL UNIQUE,
                system_prompt TEXT NOT NULL
            );
            """)
            # --- ADD THIS NEW BLOCK ---
            logging.info("Adding/Verifying default AI prompt...")
            await conn.execute(
                """
                INSERT INTO ai_prompts (class_tag, system_prompt) 
                VALUES ('default', 'You are a helpful assistant keep all your responses concise and to the point.')
                ON CONFLICT (class_tag) DO NOTHING;
                """
            )
            # --- END OF NEW BLOCK ---
            
            # --- Create an index for faster PDF searching ---
            # This 'GIN' index is specialized for text searching
            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pdfs_keywords 
            ON pdfs 
            USING GIN (to_tsvector('simple', search_keywords));
            """)
            
            logging.info("Database tables verified/created successfully.")
            
        except Exception as e:
            logging.error(f"Error creating database tables: {e}")
            raise e

async def close_db_pool():
    """
    Closes the database connection pool.
    This should be called once when the bot stops.
    """
    if pool:
        await pool.close()
        logging.info("Database connection pool closed.")