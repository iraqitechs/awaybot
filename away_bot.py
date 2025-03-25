import os
from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image

# Load environment variables
load_dotenv()
API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE = os.getenv('TELEGRAM_PHONE')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Configure Google Generative AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')  # Multimodal model

# Default away message
INITIAL_DEFAULT_AWAY_MESSAGE = "I'm currently away! I'll get back to you soon."

# Supported languages
SUPPORTED_LANGUAGES = {'english', 'arabic'}

# Image storage directory
IMAGE_DIR = "images"
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# Store away status, custom messages, and message counts
class AwayBot:
    def __init__(self):
        self.is_away = False
        self.away_until = None
        self.custom_messages = {}
        self.default_away_message = INITIAL_DEFAULT_AWAY_MESSAGE
        self.except_users = set()
        self.message_counts = {}
        self.group_replies_enabled = False
        self.ai_enabled = False
        self.ai_response_length = "medium"

bot_state = AwayBot()

# Initialize the Telegram client
client = TelegramClient('session_name', API_ID, API_HASH)

@client.on(events.NewMessage(outgoing=False))
async def handle_incoming_message(event):
    """Handle incoming messages with group toggle and away mode."""
    if bot_state.is_away and datetime.now() < bot_state.away_until:
        chat = await event.get_chat()
        if isinstance(chat, (Chat, Channel)) and not bot_state.group_replies_enabled:
            return

        sender = await event.get_sender()
        if not isinstance(sender, User):
            return

        sender_handle = f"@{sender.username.lower()}" if sender.username else None
        sender_phone = sender.phone if sender.phone else None
        sender_id = sender_handle or sender_phone or str(sender.id)

        if sender_id in bot_state.except_users:
            return

        bot_state.message_counts[sender_id] = bot_state.message_counts.get(sender_id, 0) + 1
        if bot_state.message_counts[sender_id] >= 3:
            bot_state.except_users.add(sender_id)
            await client.send_message('me', f"{sender_id} has sent {bot_state.message_counts[sender_id]} messages and has been added to the exception list.")
            return

        if sender_handle and sender_handle in bot_state.custom_messages:
            await event.reply(bot_state.custom_messages[sender_handle])
        else:
            await event.reply(bot_state.default_away_message)
    elif bot_state.is_away and datetime.now() >= bot_state.away_until:
        bot_state.is_away = False
        bot_state.away_until = None
        bot_state.message_counts.clear()

@client.on(events.NewMessage(pattern='/help-away'))
async def help_away(event):
    """Explain how to use the bot."""
    group_status = "enabled" if bot_state.group_replies_enabled else "disabled"
    ai_status = "enabled" if bot_state.ai_enabled else "disabled"
    help_text = (
        f"Welcome to your Away Bot! This bot auto-replies to messages sent to your Telegram account when you're away (group replies {group_status}, AI {ai_status}).\n\n"
        "Here’s how to use it:\n"
        "- **/away <time>** - Set away mode (e.g., `/away 3h` for 3 hours, `/away 180m` for 180 minutes).\n"
        "- **/cancel** - Stop away mode.\n"
        "- **/status** - Check away mode status.\n"
        "- **/setmessage @username <message>** - Set a custom reply (e.g., `/setmessage @john Back soon!`).\n"
        "- **/setawaymessage <message>** - Set the default away message (e.g., `/setawaymessage Out for lunch!`).\n"
        "- **/except <@username or +phonenumber>** - Exclude a user from away messages (e.g., `/except @john`).\n"
        "- **/removeexcept <@username or +phonenumber>** - Remove from exception list (e.g., `/removeexcept @john`).\n"
        "- **/togglegroupreplies** - Toggle group replies (currently {group_status}).\n"
        "- **/enable-ai** - Toggle AI integration (currently {ai_status}).\n"
        "- **/ai-explain** - Analyze replied message in English.\n"
        "- **/ai-explain <arabic|english>** - Analyze replied message in specified language.\n"
        "- **/ai-explain <arabic|english> <context>** - Analyze replied message with context in specified language.\n"
        "- **/setailength <short|medium|long>** - Set AI response length (currently {bot_state.ai_response_length}).\n"
        "- **/ai-explain-only <arabic|english> <context>** - Analyze text context only (e.g., `/ai-explain-only arabic ما هي البرمجة؟`).\n"
        "- **/ai-explain-image <arabic|english> [optional context]** - Analyze a replied image, saved to /images (reply to an image message).\n\n"
        "Special Feature: 3+ messages auto-adds a user to exceptions with a notification.\n\n"
        "Examples:\n"
        "- `/away 3h` - Away for 3 hours.\n"
        "- Reply to text with `/ai-explain` - Analyze in English.\n"
        "- Reply to text with `/ai-explain arabic` - Analyze in Arabic.\n"
        "- Reply to text with `/ai-explain english Tell me more` - Analyze with context in English.\n"
        "- `/ai-explain-only arabic ما هي البرمجة؟` - Analyze in Arabic.\n"
        "- Reply to an image with `/ai-explain-image arabic What is this?` - Analyze image in Arabic.\n\n"
        "Notes: Send commands in any chat. Replies depend on toggles and exceptions."
    )
    await event.reply(help_text)

@client.on(events.NewMessage(pattern=r'/away (\d+)(h|m)?'))
async def away(event):
    """Set away mode with minutes or hours."""
    match = event.pattern_match
    duration = int(match.group(1))
    unit = match.group(2) or 'm'
    if unit.lower() == 'h':
        minutes = duration * 60
    else:
        minutes = duration
    bot_state.is_away = True
    bot_state.away_until = datetime.now() + timedelta(minutes=minutes)
    bot_state.message_counts.clear()
    await event.reply(f"Away mode activated for {duration} {unit} (={minutes} minutes) until {bot_state.away_until.strftime('%H:%M:%S')}.")

@client.on(events.NewMessage(pattern='/cancel'))
async def cancel(event):
    """Cancel away mode."""
    if bot_state.is_away:
        bot_state.is_away = False
        bot_state.away_until = None
        bot_state.message_counts.clear()
        await event.reply("Away mode canceled.")
    else:
        await event.reply("Away mode is not active.")

@client.on(events.NewMessage(pattern=r'/setmessage @\w+ .+'))
async def set_message(event):
    """Set custom message for a specific user."""
    parts = event.raw_text.split(' ', 2)
    handle = parts[1].lower()
    message = parts[2]
    bot_state.custom_messages[handle] = message
    await event.reply(f"Custom message set for {handle}: '{message}'")

@client.on(events.NewMessage(pattern='/status'))
async def status(event):
    """Check the current away status."""
    if bot_state.is_away:
        if datetime.now() < bot_state.away_until:
            time_left = (bot_state.away_until - datetime.now()).seconds // 60
            await event.reply(f"Away mode is active. Time left: {time_left} minutes.")
        else:
            bot_state.is_away = False
            bot_state.away_until = None
            bot_state.message_counts.clear()
            await event.reply("Away mode has expired and is now deactivated.")
    else:
        await event.reply("Away mode is not active.")

@client.on(events.NewMessage(pattern=r'/setawaymessage .+'))
async def set_away_message(event):
    """Set a custom default away message."""
    message = event.raw_text.split(' ', 1)[1]
    bot_state.default_away_message = message
    await event.reply(f"Default away message updated to: '{message}'")

@client.on(events.NewMessage(pattern=r'/except (@\w+|\+\d+)'))
async def except_user(event):
    """Add a user to the exception list."""
    identifier = event.raw_text.split(' ', 1)[1]
    bot_state.except_users.add(identifier)
    await event.reply(f"{identifier} will no longer receive away messages.")

@client.on(events.NewMessage(pattern=r'/removeexcept (@\w+|\+\d+)'))
async def remove_except_user(event):
    """Remove a user from the exception list."""
    identifier = event.raw_text.split(' ', 1)[1]
    if identifier in bot_state.except_users:
        bot_state.except_users.remove(identifier)
        await event.reply(f"{identifier} removed from exception list. They will now receive away messages.")
    else:
        await event.reply(f"{identifier} is not in the exception list.")

@client.on(events.NewMessage(pattern='/togglegroupreplies'))
async def toggle_group_replies(event):
    """Toggle whether the bot replies in group chats."""
    bot_state.group_replies_enabled = not bot_state.group_replies_enabled
    status = "enabled" if bot_state.group_replies_enabled else "disabled"
    await event.reply(f"Group replies are now {status}.")

@client.on(events.NewMessage(pattern='/enable-ai'))
async def enable_ai(event):
    """Toggle AI integration with Gemini."""
    bot_state.ai_enabled = not bot_state.ai_enabled
    status = "enabled" if bot_state.ai_enabled else "disabled"
    await event.reply(f"AI integration is now {status}. Use '/ai-explain', '/ai-explain-only', or '/ai-explain-image' with optional language and context.")

@client.on(events.NewMessage(pattern=r'/setailength (short|medium|long)'))
async def set_ai_length(event):
    """Set the desired length of AI responses."""
    length = event.pattern_match.group(1).lower()
    bot_state.ai_response_length = length
    await event.reply(f"AI response length set to {length}.")

@client.on(events.NewMessage(pattern=r'^/ai-explain(?:\s+(\w+)(?:\s+(.+))?)?$'))
async def ai_explain(event):
    """Analyze a replied message with optional language and context."""
    if not bot_state.ai_enabled:
        await event.reply("AI integration is not enabled. Use '/enable-ai' first.")
        return

    if not event.reply_to_msg_id:
        await event.reply("Please reply to a message with '/ai-explain' to analyze it.")
        return

    replied_msg = await event.get_reply_message()
    if not replied_msg or not replied_msg.text:
        await event.reply("No text found in the quoted message to analyze.")
        return

    language = event.pattern_match.group(1).lower() if event.pattern_match.group(1) else "english"
    context = event.pattern_match.group(2).strip() if event.pattern_match.group(2) else ""

    if language not in SUPPORTED_LANGUAGES:
        await event.reply(f"Unsupported language '{language}'. Supported languages: {', '.join(SUPPORTED_LANGUAGES)}. Defaulting to English.")
        language = "english"

    length_instruction = f"Provide a {bot_state.ai_response_length} response."
    language_instruction = f"Respond in {language}."
    if context:
        prompt = f"{length_instruction} {language_instruction} Analyze this message: '{replied_msg.text}' and provide details based on this additional context: '{context}'"
    else:
        prompt = f"{length_instruction} {language_instruction} Analyze this message and provide details about its content: '{replied_msg.text}'"

    try:
        response = model.generate_content(prompt)
        await event.reply(f"AI Analysis: {response.text}")
    except Exception as e:
        await event.reply(f"AI Error: {str(e)}")

@client.on(events.NewMessage(pattern=r'^/ai-explain-only (\w+) (.+)$'))
async def ai_explain_only(event):
    """Generate AI response based on provided context and language, no reply needed."""
    if not bot_state.ai_enabled:
        await event.reply("AI integration is not enabled. Use '/enable-ai' first.")
        return

    language = event.pattern_match.group(1).lower()
    context = event.pattern_match.group(2).strip()

    if language not in SUPPORTED_LANGUAGES:
        await event.reply(f"Unsupported language '{language}'. Supported languages: {', '.join(SUPPORTED_LANGUAGES)}. Defaulting to English.")
        language = "english"

    if not context:
        await event.reply("Please provide context after the language (e.g., '/ai-explain-only arabic ما هي البرمجة؟').")
        return

    length_instruction = f"Provide a {bot_state.ai_response_length} response."
    language_instruction = f"Respond in {language}."
    prompt = f"{length_instruction} {language_instruction} Provide details based on this context: '{context}'"

    try:
        response = model.generate_content(prompt)
        await event.reply(f"AI Analysis: {response.text}")
    except Exception as e:
        await event.reply(f"AI Error: {str(e)}")

@client.on(events.NewMessage(pattern=r'^/ai-explain-image (\w+)(?:\s+(.+))?$'))
async def ai_explain_image(event):
    """Analyze a replied image with optional context, saving it to /images."""
    if not bot_state.ai_enabled:
        await event.reply("AI integration is not enabled. Use '/enable-ai' first.")
        return

    if not event.reply_to_msg_id:
        await event.reply("Please reply to an image message with '/ai-explain-image <arabic|english> [optional context]' to analyze it.")
        return

    replied_msg = await event.get_reply_message()
    if not replied_msg or not replied_msg.photo:
        await event.reply("Please reply to a message containing an image to analyze.")
        return

    language = event.pattern_match.group(1).lower()
    context = event.pattern_match.group(2).strip() if event.pattern_match.group(2) else ""

    if language not in SUPPORTED_LANGUAGES:
        await event.reply(f"Unsupported language '{language}'. Supported languages: {', '.join(SUPPORTED_LANGUAGES)}. Defaulting to English.")
        language = "english"

    # Download the image from the replied message
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(IMAGE_DIR, f"image_{timestamp}.jpg")
    try:
        await replied_msg.download_media(file=image_path)
    except Exception as e:
        await event.reply(f"Error downloading image: {str(e)}")
        return

    # Open and process the image
    try:
        img = Image.open(image_path)
        length_instruction = f"Provide a {bot_state.ai_response_length} response."
        language_instruction = f"Respond in {language}."
        if context:
            prompt = f"{length_instruction} {language_instruction} Analyze this image and provide details based on this additional context: '{context}'"
        else:
            prompt = f"{length_instruction} {language_instruction} Describe and analyze this image."

        response = model.generate_content([prompt, img])
        await event.reply(f"AI Analysis: {response.text}")
    except Exception as e:
        await event.reply(f"AI Error: {str(e)}")
    finally:
        if 'img' in locals():
            img.close()  # Ensure the image file is closed
        # Uncomment to remove image after processing
        # if os.path.exists(image_path):
        #     os.remove(image_path)

async def main():
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY not found in .env file.")
        return
    await client.start(phone=PHONE)
    print("Bot is running... Press Ctrl+C to stop")
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())
