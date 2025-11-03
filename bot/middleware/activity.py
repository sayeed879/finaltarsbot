import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Update
from asyncpg import Pool
import asyncio
from bot.db import user_queries

class UserActivityMiddleware(BaseMiddleware):
    """
    This middleware automatically updates the 'last_active'
    timestamp for a user on *every* incoming update.
    """
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Awaitable[Any]:
        
        # We only care about events that have a user
        if event.message or event.callback_query:
            user = event.message.from_user if event.message else event.callback_query.from_user
            
            # Get the db_pool from the data
            db_pool: Pool = data.get('db_pool')
            
            if db_pool:
                try:
                    # Run this in the background, don't wait for it
                    asyncio.create_task(
                        user_queries.update_user_last_active(db_pool, user.id)
                    )
                except Exception as e:
                    logging.warning(f"Failed to update last_active in middleware: {e}")

        # Continue to the next handler
        return await handler(event, data)