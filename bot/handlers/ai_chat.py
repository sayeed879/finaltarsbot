import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from redis.asyncio import Redis

import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from google.api_core import retry

# Our component imports
from bot.fsm.states import UserFlow
from bot.db import user_queries, ai_queries
from bot.config import GEMINI_API_KEY, ADMIN_ID

router = Router()
MAX_HISTORY_MESSAGES = 4  # Remembers 2 user, 2 bot messages
MAX_INPUT_CHARS = 1000  # Limit for user input

# Initialize the model globally
MODEL = None
generation_config = GenerationConfig(
    temperature=0.7,
    top_p=1.0,
    top_k=40,
    max_output_tokens=250,
)

def initialize_ai_model():
    """Initialize the AI model with proper error handling"""
    global MODEL
    if not GEMINI_API_KEY:
        logging.critical("GEMINI_API_KEY is not set. The AI feature will not work.")
        return False

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Try to initialize Flash model first
        try:
            MODEL = genai.GenerativeModel('gemini-2.5-flash', generation_config=generation_config)
            logging.info("Successfully initialized Gemini flash model")
            return True
        except Exception as e:
            logging.error(f"Failed to initialize Gemini model: {e}")
            return False
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")
        return False

# Initialize the model when module loads
initialize_ai_model()

async def call_my_ai_api(bot: Bot, user_id: int, system_prompt: str, history: list, new_prompt: str) -> str:
    """
    Connects to the Gemini API and generates a response using the native async client.
    Includes retry logic and proper error handling.
    """
    if not MODEL:
        if initialize_ai_model():
            logging.info("Successfully re-initialized AI model")
        else:
            logging.error(f"Gemini API initialization failed for user {user_id}")
            return "❌ AI Error: Could not initialize AI model. Please contact the admin."

    try:
        # Truncate long messages
        if len(new_prompt) > MAX_INPUT_CHARS:
            new_prompt = new_prompt[:MAX_INPUT_CHARS] + "\n\n(Message was truncated)"

        # Prepare conversation with proper prompt engineering
        conversation = []
        
        # Add system prompt with clear role definition
        conversation.append({
            "role": "user",
            "parts": [{
                "text": f"You are an AI assistant. Follow these instructions: {system_prompt}"
            }]
        })
        
        # Add relevant history with proper formatting
        if history:
            conversation.extend(history[-MAX_HISTORY_MESSAGES:])
        
        # Add the new prompt
        conversation.append({
            "role": "user",
            "parts": [{"text": new_prompt}]
        })

        # Multiple retries with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Generate response with safety checks
                response = await MODEL.generate_content_async(conversation)
                
                if response and hasattr(response, 'text') and response.text:
                    return response.text.strip()
                
                raise ValueError("Empty or invalid response from AI model")
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + 1  # Exponential backoff
                    logging.warning(f"AI attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise  # Re-raise on final attempt

    except Exception as e:
        error_msg = str(e)
        logging.error(f"AI Error for user {user_id}: {error_msg}")
        
        # Notify admin of critical errors
        try:
            await bot.send_message(
                ADMIN_ID,
                f"❌ AI ERROR for user {user_id}:\n{error_msg[:500]}"
            )
        except Exception as notify_error:
            logging.error(f"Failed to notify admin: {notify_error}")
        
        # User-friendly error message
        return "❌ Sorry, I encountered an error. Please try again in a moment."
        try:
            await bot.send_message(
                ADMIN_ID, 
                f"❌ CRITICAL AI FAILURE: Gemini API failed for user {user_id}. Error: {e}"
            )
        except Exception as admin_e:
            logging.error(f"Failed to even notify admin: {admin_e}")
        return "❌ AI Error: The AI service failed to respond. The issue has been logged."

# --- 1. Trigger the AI Mode ---
@router.message(F.text == "💬 Chat with Ai")
async def start_ai_chat(message: Message, state: FSMContext, db_pool):
    user_id = message.from_user.id
    await user_queries.update_user_last_active(db_pool, user_id)
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer("Please type /start to register first.")
        return
    
    if not user.is_premium and user.ai_limit_remaining <= 0:
        await message.answer(
            "You are out of free AI queries for today. "
            "Use /upgrade to get more."
        )
        return

    await state.set_state(UserFlow.AwaitingAIPrompt)
    await state.update_data(history=[])
    
    await message.answer(
        "You are now in **AI Chat Mode**. "
        "I will remember our last few messages.\n\nAsk me anything!\nType /stop to exit."
    )

# --- 2. Handle the user's AI prompt ---
@router.message(UserFlow.AwaitingAIPrompt)
async def handle_ai_prompt(
    message: Message, 
    state: FSMContext, 
    db_pool,
    bot: Bot, 
    ai_cache: Redis
):
    user_id = message.from_user.id
    prompt = message.text
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer("An error occurred. Please type /start.")
        return

    # --- Check Global Cache First ---
    cache_key = f"ai_cache:{prompt.lower().strip()}"
    try:
        cached_response = await ai_cache.get(cache_key)
        if cached_response:
            logging.info(f"AI Cache HIT for user {user_id}")
            await message.answer(cached_response + "\n\n*(This was a cached response)*")
            return
    except Exception as e:
        logging.error(f"Redis cache GET error: {e}")

    logging.info(f"AI Cache MISS for user {user_id}")
    
    # --- Cache Miss: We must call the real AI ---
    
    # 1. Decrement Limit (if not premium)
    if not user.is_premium:
        success = await user_queries.decrement_ai_limit(db_pool, user_id)
        if not success:
            await message.answer("You are out of AI queries. Use /upgrade.")
            await state.clear()
            return
            
    # 2. Get data for AI
    fsm_data = await state.get_data()
    history = fsm_data.get("history", [])
    system_prompt = await ai_queries.get_ai_prompt(db_pool, user.selected_class)

    # 3. Call AI (with a typing indicator)
    await message.bot.send_chat_action(chat_id=user_id, action="typing")
    
    ai_response = await call_my_ai_api(bot, user_id, system_prompt, history, prompt)

    # 4. Send response to user
    await message.answer(ai_response)
    
    # 5. Update history (This format is for the new 1.x.x library)
    history.append({"role": "user", "parts": [{"text": prompt}]})
    history.append({"role": "assistant", "parts": [{"text": ai_response}]})
    
    # 6. Trim history
    if len(history) > MAX_HISTORY_MESSAGES:
        history = history[-MAX_HISTORY_MESSAGES:]
        
    await state.update_data(history=history)

    # 7. Save to global cache
    try:
        await ai_cache.set(cache_key, ai_response, ex=3600)
    except Exception as e:
        logging.error(f"Redis cache SET error: {e}")