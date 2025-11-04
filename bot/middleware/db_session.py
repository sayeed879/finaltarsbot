from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import asyncpg
import logging

class DBSessionMiddleware(BaseMiddleware):
    """
    Middleware to manage database connection acquisition and release.
    Uses asyncpg connection pool.
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Execute middleware."""
        if 'db_pool' not in data:
            logging.warning("No database pool available in middleware data")
            return await handler(event, data)
            
        pool: asyncpg.Pool = data['db_pool']
        
        # Get connection from pool
        async with pool.acquire() as conn:
            # Add connection to data dict
            data['db_conn'] = conn
            try:
                # Process request
                return await handler(event, data)
            except Exception as e:
                # Log error but don't handle it - let it propagate
                logging.error(f"Error in database middleware: {e}")
                raise