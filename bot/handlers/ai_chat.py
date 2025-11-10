import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from redis.asyncio import Redis

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

# Our component imports
from bot.fsm.states import UserFlow
from bot.db import user_queries, ai_queries
from bot.config import GEMINI_API_KEY, ADMIN_ID

router = Router()
MAX_HISTORY_MESSAGES = 4
MAX_INPUT_CHARS = 1000
CACHE_EXPIRY = 7200

# (All your model initialization code... no changes needed here)
MODEL = None
generation_config = GenerationConfig(
    temperature=0.7,
    top_p=0.95,
    top_k=40,
    max_output_tokens=500,
)

def initialize_ai_model():
    """Initialize the AI model with proper error handling"""
    global MODEL
    if not GEMINI_API_KEY:
        logging.critical("GEMINI_API_KEY is not set. The AI feature will not work.")
        return False

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        MODEL = genai.GenerativeModel(
            'gemini-2.5-flash',
            generation_config=generation_config,
            safety_settings=[
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        )
        logging.info("✅ Successfully initialized Gemini Flash model")
        return True
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")
        return False

initialize_ai_model()

async def call_my_ai_api(
    bot: Bot, 
    user_id: int, 
    system_prompt: str, 
    history: list, 
    new_prompt: str
) -> str:
    """
    Connects to the Gemini API and generates a response with proper error handling.
    (This function is unchanged)
    """
    if not MODEL:
        if not initialize_ai_model():
            logging.error(f"Gemini API initialization failed for user {user_id}")
            return (
                "❌ <b>AI Service Unavailable</b>\n\n"
                "The AI service is currently unavailable. "
                "Please try again later or contact support."
            )

    try:
        # (All your existing retry logic... no changes needed)
        # ...
        truncation_notice = ""
        if len(new_prompt) > MAX_INPUT_CHARS:
            new_prompt = new_prompt[:MAX_INPUT_CHARS]
            truncation_notice = "\n\n<i>(Your message was truncated due to length limits)</i>"

        conversation = []
        system_instruction = (
            f"{system_prompt}\n\n"
            "Important: Keep responses concise but informative. "
            "Aim for less than 100 words unless more detail is specifically requested."
        )
        conversation.append({"role": "user", "parts": [{"text": system_instruction}]})
        
        if history:
            recent_history = history[-MAX_HISTORY_MESSAGES:]
            conversation.extend(recent_history)
        
        conversation.append({"role": "user", "parts": [{"text": new_prompt}]})

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await asyncio.wait_for(
                    MODEL.generate_content_async(conversation),
                    timeout=30.0
                )
                
                if response and hasattr(response, 'text') and response.text:
                    response_text = response.text.strip()
                    if truncation_notice:
                        response_text += truncation_notice
                    return response_text
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    raise ValueError("Empty response from AI model")
                
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt)
                    logging.warning(f"AI timeout attempt {attempt + 1}/{max_retries} for user {user_id}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt)
                    logging.warning(f"AI attempt {attempt + 1}/{max_retries} failed for user {user_id}: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise
    except asyncio.TimeoutError:
        # (All your existing error handling... no changes needed)
        # ...
        logging.error(f"AI timeout for user {user_id}")
        return "⏱️ <b>Response Timeout</b>\n\nThe AI took too long to respond. Please try a simpler question."
    except Exception as e:
        error_msg = str(e)
        logging.error(f"AI Error for user {user_id}: {error_msg}")
        
        try:
            if "quota" in error_msg.lower() or "limit" in error_msg.lower():
                await bot.send_message(ADMIN_ID, f"🚨 <b>CRITICAL: AI API Quota Issue</b>\n\nUser: {user_id}\nError: {error_msg[:300]}")
        except Exception:
            pass
        
        if "quota" in error_msg.lower() or "resource" in error_msg.lower():
            return ("❌ <b>Service Temporarily Unavailable</b>\n\n"
                    "The AI service has reached its usage limit. "
                    "Please try again in a few minutes.")
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
            return ("⚠️ <b>Content Policy Violation</b>\n\n"
                    "Your message was flagged by the content filter. "
                    "Please rephrase your question and try again.")
        else:
            return ("❌ <b>AI Error</b>\n\n"
                    "Sorry, I encountered an error processing your request. "
                    "Please try again or rephrase your question.")

# --- 1. Trigger the AI Mode (Unchanged) ---
@router.message(Command("ai"), StateFilter('*'))
@router.message(F.text == "💬 Chat with Ai", StateFilter('*')) 
async def start_ai_chat(message: Message, state: FSMContext, db_pool):
    # (This function is unchanged)
    await state.clear()
    user_id = message.from_user.id
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer("❌ <b>Not Registered</b>\n\nPlease type /start to register first.")
        return
    
    if not user.is_premium and user.ai_limit_remaining <= 0:
        await message.answer(
            "❌ <b>AI Limit Reached</b>\n\n"
            "You have used all your free AI queries for today.\n\n"
            "Use /upgrade to get premium access!"
        )
        return

    await state.set_state(UserFlow.AwaitingAIPrompt)
    await state.update_data(history=[])
    
      
    welcome_message = (
        "🤖 <b>AI Chat Mode Activated!</b>\n\n"
        "<b>I'm ready to help you with:</b>\n"
        "• Academic questions and explanations\n"
        "• Study tips and strategies\n"
        "• Concept clarifications\n"
        "• Problem solving guidance\n\n"
    )
    if not user.is_premium:
        welcome_message += f"<b>Queries Remaining Today:</b> {user.ai_limit_remaining}/10\n\n"
    welcome_message += "<i>Ask me anything! Type /stop to exit chat mode.</i>"
    
    await message.answer(welcome_message)


# <--- THIS IS THE NEW WORKER FUNCTION ---
# It contains all the "slow" logic that used to be in your handler
async def process_ai_request_task(
    message: Message,
    user_id: int,
    prompt: str,
    state: FSMContext,
    db_pool,
    bot: Bot,
    ai_cache: Redis
):
    """
    This function runs in the background.
    It does all the slow work: cache, AI, DB updates, and sending the reply.
    """
    try:
        # --- Check Global Cache First (WITH PROPER ERROR HANDLING) ---
        cache_key = f"ai_cache:{prompt.lower().strip()[:100]}"
        try:
            cached_response = await ai_cache.get(cache_key)
            if cached_response:
                logging.info(f"✅ AI Cache HIT for user {user_id}")
                # Use .reply() so it's in context
                await message.reply(
                    f"{cached_response}\n\n"
                    f"<i>💾 (Cached response)</i>"
                )
                return # Job done
        except Exception as e:
            logging.warning(f"Redis cache GET error (non-fatal): {e}")

        logging.info(f"❌ AI Cache MISS for user {user_id} - Calling AI API")

        # --- Show typing indicator ---
        await bot.send_chat_action(chat_id=user_id, action="typing")
        
        # --- Get data for AI ---
        fsm_data = await state.get_data()
        history = fsm_data.get("history", [])
        user = await user_queries.get_user(db_pool, user_id) # Re-fetch user
        system_prompt = await ai_queries.get_ai_prompt(db_pool, user.selected_class)

        # --- Call AI ---
        ai_response = await call_my_ai_api(bot, user_id, system_prompt, history, prompt)

        # --- Check for AI errors BEFORE decrementing ---
        if ai_response.startswith("❌") or ai_response.startswith("⚠️") or ai_response.startswith("⏱️"):
            await message.reply(ai_response)
            # We DON'T decrement the limit because it failed
            return

        # --- Decrement Limit (if not premium) ---
        remaining_queries = user.ai_limit_remaining
        if not user.is_premium:
            success = await user_queries.decrement_ai_limit(db_pool, user_id)
            if success:
                remaining_queries -= 1
        
        # --- Send response to user ---
        response_message = ai_response
        
        if not user.is_premium:
            response_message += (
                f"\n\n<i>💬 Queries remaining today: {remaining_queries}/10</i>"
            )
        
        await message.reply(response_message) # Use .reply()
        
        # --- Update history ---
        history.append({"role": "user", "parts": [{"text": prompt}]})
        history.append({"role": "model", "parts": [{"text": ai_response}]})
        
        if len(history) > MAX_HISTORY_MESSAGES * 2:
            history = history[-MAX_HISTORY_MESSAGES * 2:]
            
        await state.update_data(history=history)

        # --- Save to global cache ---
        try:
            await ai_cache.set(cache_key, ai_response, ex=CACHE_EXPIRY)
            logging.info(f"✅ Cached AI response for query: {prompt[:50]}")
        except Exception as e:
            logging.warning(f"Redis cache SET error (non-fatal): {e}")
        
        logging.info(
            f"User {user_id} AI query processed. "
            f"Remaining: {remaining_queries if not user.is_premium else 'unlimited'}"
        )
    except Exception as e:
        # Catch-all for any error in the background task
        logging.error(f"Error in process_ai_request_task for user {user_id}: {e}")
        try:
            await message.reply("❌ An unexpected error occurred. Please try again.")
        except Exception as e_reply:
            logging.error(f"Failed to even send error reply: {e_reply}")


# <--- THIS IS THE MODIFIED, FAST HANDLER ---
@router.message(UserFlow.AwaitingAIPrompt, ~Command("stop"))
async def handle_ai_prompt(
    message: Message, 
    state: FSMContext, 
    db_pool,
    bot: Bot, 
    ai_cache: Redis
):
    """
    Process AI chat message - ONLY in AI chat state
    This handler is now VERY FAST. It only validates
    and starts the background task.
    """
    user_id = message.from_user.id
    prompt = message.text
    
    # --- 1. Do all FAST validation ---
    if not prompt or len(prompt.strip()) == 0:
        await message.answer(
            "❌ <b>Empty Message</b>\n\n"
            "Please send a valid question or message.\n"
            "Type /stop to exit chat mode."
        )
        return
    
    if len(prompt) < 3:
        await message.answer(
            "❌ <b>Message Too Short</b>\n\n"
            "Please ask a more detailed question.\n"
            "Type /stop to exit chat mode."
        )
        return
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer(
            "❌ <b>Error</b>\n\n"
            "An error occurred. Please type /start."
        )
        await state.clear()
        return

    # --- 2. Check Limit (FAST) ---
    if not user.is_premium and user.ai_limit_remaining <= 0:
        await message.answer(
            "❌ <b>AI Limit Reached</b>\n\n"
            "You have used all your AI queries for today.\n"
            "Use /upgrade for unlimited access!"
        )
        await state.clear()
        return
            
    # --- 3. Start the background task ---
    # This is the most important part.
    # We schedule the slow function to run and DO NOT wait for it.
    asyncio.create_task(
        process_ai_request_task(
            message=message,
            user_id=user_id,
            prompt=prompt,
            state=state,
            db_pool=db_pool,
            bot=bot,
            ai_cache=ai_cache
        )
    )

    # --- 4. Return immediately ---
    # This function finishes right here, in less than a second.
    # Telegram gets its "OK" response and will not retry.
    # The asyncio.create_task will run in the background.
    return