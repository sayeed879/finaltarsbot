from typing import Any, Awaitable, Callable, Dict, MutableMapping
import time
from collections import defaultdict
import asyncio
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
import logging

class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware for throttling user requests.
    Limits:
    - Default: 1 message per second
    - Burst: 30 messages per minute
    - Command specific limits configurable
    """

    def __init__(self):
        self.rates: MutableMapping[int, list] = defaultdict(list)  # user_id -> [timestamps]
        self.command_rates: MutableMapping[int, Dict[str, list]] = defaultdict(lambda: defaultdict(list))  # user_id -> command -> [timestamps]
        self.locks: MutableMapping[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        
        # Configure rate limits (in seconds)
        self.default_rate = 1.0  # 1 second between regular messages
        self.burst_limit = 30    # max messages per minute
        self.command_limits = {
            "start": 5.0,        # 5 seconds between /start commands
            "help": 5.0,         # 5 seconds between /help commands
            "pdf_search": 3.0,   # 3 seconds between searches
            "ai_chat": 1.0,      # 1 second between AI messages
            "upgrade": 5.0,     # 5 seconds between upgrade attempts
        }
    
    def _clean_old_timestamps(self, timestamps: list, window: int = 60) -> list:
        """Remove timestamps older than the window (in seconds)"""
        current_time = time.time()
        return [ts for ts in timestamps if current_time - ts < window]
    
    async def _check_rate_limit(
        self, 
        user_id: int, 
        command: str = None
    ) -> tuple[bool, float]:
        """
        Check if request should be throttled.
        Returns (is_throttled, wait_time).
        """
        current_time = time.time()
        
        # Get appropriate rate limit
        rate_limit = self.command_limits.get(command, self.default_rate)
        
        async with self.locks[user_id]:
            # Clean up old timestamps
            if command:
                timestamps = self.command_rates[user_id][command] = \
                    self._clean_old_timestamps(self.command_rates[user_id][command])
            else:
                timestamps = self.rates[user_id] = \
                    self._clean_old_timestamps(self.rates[user_id])
            
            # Check burst limit (only for non-command messages)
            if not command and len(timestamps) >= self.burst_limit:
                wait_time = 60 - (current_time - timestamps[0])
                return True, max(0, wait_time)
            
            # Check rate limit
            if timestamps and current_time - timestamps[-1] < rate_limit:
                wait_time = rate_limit - (current_time - timestamps[-1])
                return True, wait_time
            
            # Add new timestamp
            timestamps.append(current_time)
            return False, 0
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Execute middleware."""
        # Extract user_id and command
        user = None
        command = None
        
        if isinstance(event, Message):
            user = event.from_user
            if event.text and event.text.startswith('/'):
                command = event.text.split()[0][1:].split('@')[0]
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            if event.data:
                command = event.data.split(':')[0]
        
        if user:
            is_throttled, wait_time = await self._check_rate_limit(user.id, command)
            
            if is_throttled:
                logging.info(f"Throttled user {user.id} for {wait_time:.1f}s (command: {command})")
                
                if isinstance(event, Message):
                    await event.answer(
                        f"⚠️ Please wait {wait_time:.1f} seconds before sending another message."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        f"⚠️ Please wait {wait_time:.1f} seconds.",
                        show_alert=True
                    )
                return
        
        # Process event if not throttled
        return await handler(event, data)