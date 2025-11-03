import asyncpg
import logging
from typing import Optional

# A default prompt if a class has no specific one
DEFAULT_SYSTEM_PROMPT = "You are a helpful general-purpose assistant."

async def get_ai_prompt(pool: asyncpg.Pool, class_tag: str) -> str:
    """
    Fetches the system prompt for a given class.
    Returns a default prompt if a specific one isn't found.
    """
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT system_prompt FROM ai_prompts WHERE class_tag = $1", 
                class_tag
            )
            
            if row:
                return row['system_prompt']
            
            # If no specific prompt, get a 'default' one
            default_row = await conn.fetchrow(
                "SELECT system_prompt FROM ai_prompts WHERE class_tag = 'default'"
            )
            
            if default_row:
                return default_row['system_prompt']

        except Exception as e:
            logging.error(f"Error fetching AI prompt for class {class_tag}: {e}")
        
        # Fallback in case of error
        return DEFAULT_SYSTEM_PROMPT