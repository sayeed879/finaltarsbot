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
MAX_HISTORY_MESSAGES = 6
MAX_INPUT_CHARS = 2000
CACHE_EXPIRY = 7200

# Initialize the model globally
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
            'gemini-1.5-flash',
            generation_config=generation_config,
            safety_settings={
                'HARASSMENT': 'BLOCK_NONE',
                'HATE_SPEECH': 'BLOCK_NONE',
                'SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                'DANGEROUS_CONTENT': 'BLOCK_NONE',
            }
        )
        logging.info("✅ Successfully initialized Gemini Flash model")
        return True
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")
        return False

# Initialize the model when module loads
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
        # Input validation and truncation
        truncation_notice = ""
        if len(new_prompt) > MAX_INPUT_CHARS:
            new_prompt = new_prompt[:MAX_INPUT_CHARS]
            truncation_notice = "\n\n<i>(Your message was truncated due to length limits)</i>"

        # Prepare conversation with system prompt
        conversation = []
        
        # Add system instructions
        system_instruction = (
            f"{system_prompt}\n\n"
            "Important: Keep responses concise but informative. "
            "Aim for less than 150 words unless more detail is specifically requested."
        )
        
        conversation.append({
            "role": "user",
            "parts": [{"text": system_instruction}]
        })
        
        # Add recent conversation history
        if history:
            recent_history = history[-MAX_HISTORY_MESSAGES:]
            conversation.extend(recent_history)
        
        # Add the new prompt
        conversation.append({
            "role": "user",
            "parts": [{"text": new_prompt}]
        })

        # Multiple retries with exponential backoff
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Generate response with timeout
                response = await asyncio.wait_for(
                    MODEL.generate_content_async(conversation),
                    timeout=30.0
                )
                
                # Extract and validate response
                if response and hasattr(response, 'text') and response.text:
                    response_text = response.text.strip()
                    
                    if truncation_notice:
                        response_text += truncation_notice
                    
                    return response_text
                
                # Handle empty responses
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    raise ValueError("Empty response from AI model")
                
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt)
                    logging.warning(
                        f"AI timeout attempt {attempt + 1}/{max_retries} for user {user_id}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt)
                    logging.warning(
                        f"AI attempt {attempt + 1}/{max_retries} failed for user {user_id}: {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

    except asyncio.TimeoutError:
        logging.error(f"AI timeout for user {user_id}")
        return "⏱️ <b>Response Timeout</b>\n\nThe AI took too long to respond. Please try a simpler question."
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"AI Error for user {user_id}: {error_msg}")
        
        # Notify admin of critical errors
        try:
            if "quota" in error_msg.lower() or "limit" in error_msg.lower():
                await bot.send_message(
                    ADMIN_ID,
                    f"🚨 <b>CRITICAL: AI API Quota Issue</b>\n\n"
                    f"User: {user_id}\n"
                    f"Error: {error_msg[:300]}"
                )
        except Exception:
            pass
        
        # User-friendly error messages
        if "quota" in error_msg.lower() or "resource" in error_msg.lower():
            return (
                "❌ <b>Service Temporarily Unavailable</b>\n\n"
                "The AI service has reached its usage limit. "
                "Please try again in a few minutes."
            )
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
            return (
                "⚠️ <b>Content Policy Violation</b>\n\n"
                "Your message was flagged by the content filter. "
                "Please rephrase your question and try again."
            )
        else:
            return (
                "❌ <b>AI Error</b>\n\n"
                "Sorry, I encountered an error processing your request. "
                "Please try again or rephrase your question."
            )

# --- 1. Trigger the AI Mode (FIXED: Added Command filter to prevent conflicts) ---
@router.message(Command("ai"), StateFilter(None))
@router.message(F.text == "💬 Chat with Ai", StateFilter(None))
async def start_ai_chat(message: Message, state: FSMContext, db_pool):
    """Start AI chat mode - ONLY when not in another state"""
    user_id = message.from_user.id
    
    user = await user_queries.get_user(db_pool, user_id)
    if not user:
        await message.answer(
            "❌ <b>Not Registered</b>\n\n"
            "Please type /start to register first."
        )
        return
    
    # Check AI limit
    if not user.is_premium and user.ai_limit_remaining <= 0:
        await message.answer(
            "❌ <b>AI Limit Reached</b>\n\n"
            "You have used all your free AI queries for today.\n\n"
            "<b>Free Plan:</b> 10 queries per day (resets at 00:00 UTC)\n"
            "<b>Premium Plan:</b> 100 queries per day\n\n"
            "💡 Upgrade to premium:\n"
            "• 100 AI queries per day (10x more!)\n"
            "• 50 PDF downloads per day\n"
            "• All locked PDFs unlocked\n\n"
            "Use /upgrade to get premium access!"
        )
        return

    # Enter AI chat mode
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
        welcome_message += (
            f"<b>Queries Remaining Today:</b> {user.ai_limit_remaining}/10\n\n"
        )
    
    welcome_message += (
        "<b>💡 Tips for Best Results:</b>\n"
        "• Ask clear, specific questions\n"
        "• Provide context when needed\n"
        "• I remember our last few exchanges\n\n"
        "<i>Ask me anything! Type /stop to exit chat mode.</i>"
    )
    
    await message.answer(welcome_message)

# --- 2. Handle the user's AI prompt (FIXED: Better state handling and Redis error handling) ---
@router.message(UserFlow.AwaitingAIPrompt, ~Command("stop"))
async def handle_ai_prompt(
    message: Message, 
    state: FSMContext, 
    db_pool,
    bot: Bot, 
    ai_cache: Redis
):
    """Process AI chat message - ONLY in AI chat state"""
    user_id = message.from_user.id
    prompt = message.text
    
    # Validate input
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

    # --- Check Global Cache First (WITH PROPER ERROR HANDLING) ---
    cache_key = f"ai_cache:{prompt.lower().strip()[:100]}"  # Limit key length
    cached_response = None
    
    try:
        cached_response = await ai_cache.get(cache_key)
        if cached_response:
            logging.info(f"✅ AI Cache HIT for user {user_id}")
            await message.answer(
                f"{cached_response}\n\n"
                f"<i>💾 (Cached response)</i>"
            )
            return
    except Exception as e:
        logging.warning(f"Redis cache GET error (non-fatal): {e}")
        # Continue without cache - don't fail the request

    logging.info(f"❌ AI Cache MISS for user {user_id} - Calling AI API")
    
    # --- Decrement Limit (if not premium) ---
    if not user.is_premium:
        success = await user_queries.decrement_ai_limit(db_pool, user_id)
        if not success:
            await message.answer(
                "❌ <b>AI Limit Reached</b>\n\n"
                "You have used all your AI queries for today.\n"
                "Use /upgrade for unlimited access!"
            )
            await state.clear()
            return
        
        # Get updated user
        user = await user_queries.get_user(db_pool, user_id)
            
    # --- Get data for AI ---
    fsm_data = await state.get_data()
    history = fsm_data.get("history", [])
    system_prompt = await ai_queries.get_ai_prompt(db_pool, user.selected_class)

    # --- Show typing indicator ---
    await message.bot.send_chat_action(chat_id=user_id, action="typing")
    
    # --- Call AI ---
    ai_response = await call_my_ai_api(bot, user_id, system_prompt, history, prompt)

    # --- Send response to user ---
    response_message = ai_response
    
    # Add remaining queries info for free users
    if not user.is_premium:
        response_message += (
            f"\n\n<i>💬 Queries remaining today: {user.ai_limit_remaining}/10</i>"
        )
    
    await message.answer(response_message)
    
    # --- Update history ---
    history.append({"role": "user", "parts": [{"text": prompt}]})
    history.append({"role": "model", "parts": [{"text": ai_response}]})
    
    # Trim history
    if len(history) > MAX_HISTORY_MESSAGES * 2:  # *2 because we store both user and model
        history = history[-MAX_HISTORY_MESSAGES * 2:]
        
    await state.update_data(history=history)

    # --- Save to global cache (WITH PROPER ERROR HANDLING) ---
    if not ai_response.startswith("❌") and not ai_response.startswith("⚠️"):
        try:
            await ai_cache.set(cache_key, ai_response, ex=CACHE_EXPIRY)
            logging.info(f"✅ Cached AI response for query: {prompt[:50]}")
        except Exception as e:
            logging.warning(f"Redis cache SET error (non-fatal): {e}")
            # Continue - caching failure shouldn't break the flow
    
    logging.info(
        f"User {user_id} AI query processed. "
        f"Remaining: {user.ai_limit_remaining if not user.is_premium else 'unlimited'}"
    )