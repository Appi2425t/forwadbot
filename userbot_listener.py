"""
Telegram Forwarding Tool — Userbot Listener + Bot API Relayer
Single asyncio process: Telethon client listens, python-telegram-bot relays.
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from aiohttp import web

# ---------------------------------------------------------------------------
# Config — validate all required env vars at startup
# ---------------------------------------------------------------------------
REQUIRED_VARS = {
    "API_ID": "Telegram API ID (from my.telegram.org)",
    "API_HASH": "Telegram API hash (from my.telegram.org)",
    "SESSION_STRING": "Pre-generated Telethon session string",
    "SOURCE_GROUP_ID": "Numeric ID of the source group to listen in",
    "BOT_TOKEN": "Bot token (from @BotFather)",
    "DEST_GROUP_ID": "Numeric ID of the destination group",
}


def _load_config():
    load_dotenv()
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        lines = ["Missing required environment variables:"]
        for name in missing:
            lines.append(f"  {name:20s} — {REQUIRED_VARS[name]}")
        print("\n".join(lines), file=sys.stderr)
        sys.exit(1)

    return {
        "API_ID": int(os.environ["API_ID"]),
        "API_HASH": os.environ["API_HASH"],
        "SESSION_STRING": os.environ["SESSION_STRING"],
        "SOURCE_GROUP_ID": int(os.environ["SOURCE_GROUP_ID"]),
        "BOT_TOKEN": os.environ["BOT_TOKEN"],
        "DEST_GROUP_ID": int(os.environ["DEST_GROUP_ID"]),
    }


cfg = _load_config()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("forwarder")

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
userbot = TelegramClient(StringSession(cfg["SESSION_STRING"]), cfg["API_ID"], cfg["API_HASH"])
bot = Bot(token=cfg["BOT_TOKEN"])

# ---------------------------------------------------------------------------
# Code detection & pending codes store
# ---------------------------------------------------------------------------
# Matches: **Code**: `stakecomlljg2dcbby9unz` or Code: stakecomlljg2dcbby9unz
CODE_PATTERNS = [
    re.compile(r"\*{0,2}Code\*{0,2}[:\s`]+([A-Za-z0-9]{6,30})`?", re.IGNORECASE),
    re.compile(r"^Code:\s*([A-Za-z0-9]{6,30})$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"Code:\s*([A-Za-z0-9]{6,30})", re.IGNORECASE),
]

pending_codes: list[dict] = []
claimed_codes: set[str] = set()
MAX_PENDING = 50

# ---------------------------------------------------------------------------
# NFT-style Username Generator
# ---------------------------------------------------------------------------
import random

# NFT-themed word lists for generating cool, rare usernames
NFT_PREFIXES = [
    # Crypto/Web3 themed
    "Crypto", "Blockchain", "Web3", "DeFi", "NFT", "Meta", "Digital",
    # Rare/Mythical
    "Rare", "Mythic", "Legend", "Phantom", "Shadow", "Neon", "Cyber",
    "Cosmic", "Quantum", "Alpha", "Omega", "Zero", "Genesis", "Prime",
    # Luxury/Premium
    "Gold", "Diamond", "Platinum", "Royal", "Elite", "Supreme", "Apex",
    # Gaming
    "Pixel", "Retro", "Turbo", "Mega", "Ultra", "Hyper", "Neo",
    # Sci-Fi
    "Galaxy", "Stellar", "Nova", "Pulse", "Flux", "Vortex", "Nexus",
    "Zenith", "Aether", "Cypher", "Daemon", "Vector",
]

NFT_SUFFIXES = [
    # Status/Power
    "Lord", "King", "Master", "Sage", "Wizard", "Mage", "Knight",
    "Hunter", "Slayer", "Guardian", "Warrior", "Titan", "Giant",
    # Animals (mythical)
    "Dragon", "Phoenix", "Wolf", "Tiger", "Lion", "Eagle", "Hawk",
    "Panther", "Raven", "Cobra", "Falcon", "Viper",
    # Objects/Symbols
    "Coin", "Token", "Vault", "Fortune", "Treasure", "Gem", "Stone",
    "Crystal", "Orb", "Crown", "Blade", "Shield",
    # Abstract
    "Mind", "Soul", "Spirit", "Force", "Power", "Edge", "Core",
    "Matrix", "Prism", "Spectrum",
]

NFT_WORDS = [
    # Single powerful words
    "Apex", "Blaze", "Cipher", "Dusk", "Echo", "Frost",
    "Glimmer", "Havoc", "Inferno", "Jinx", "Karma", "Lunar",
    "Mystic", "Nebula", "Obsidian", "Prism", "Rune", "Shadow",
    "Thorn", "Umbra", "Void", "Wraith", "Xenon", "Zenith",
    "Arctic", "Bolt", "Cosmos", "Delta", "Ember", "Fury",
    "Ghost", "Hollow", "Iron", "Jade", "Keystone", "Lotus",
    "Monarch", "Nimbus", "Oracle", "Phantom", "Rogue", "Spark",
    "Tempest", "Unity", "Viper", "Wanderer", "Xeno", "Yeti", "Zephyr",
]

# Numbers that look cool
COOL_NUMBERS = ["0", "1", "42", "69", "77", "88", "99", "100", "1337", "420", "777", "888", "999"]

def generate_nft_username(style: str = "random") -> str:
    """
    Generate a cool NFT-style username.
    Styles: 'rare', 'cyber', 'mythic', 'clean', 'random'
    """
    style = style.lower()
    
    if style == "rare":
        # Short, punchy, rare-looking
        return random.choice(NFT_WORDS).lower() + random.choice(COOL_NUMBERS)
    
    elif style == "cyber":
        # Cyber/tech themed
        prefix = random.choice(["Cyber", "Neo", "Quantum", "Pixel", "Turbo", "Hyper"])
        suffix = random.choice(["Punk", "Net", "Tech", "Bot", "Node", "Core", "Flux"])
        num = random.choice(COOL_NUMBERS)
        return f"{prefix}{suffix}{num}".lower()
    
    elif style == "mythic":
        # Mythical/legendary
        prefix = random.choice(["Mythic", "Legend", "Ancient", "Eternal", "Divine"])
        suffix = random.choice(["Soul", "Force", "Blade", "Crown", "Orb"])
        return f"{prefix}{suffix}".lower()
    
    elif style == "clean":
        # Clean, minimal
        word = random.choice(NFT_WORDS).lower()
        num = random.choice(["", "_", random.choice(COOL_NUMBERS)])
        return word + num
    
    else:  # random
        combo = random.randint(1, 4)
        if combo == 1:
            # Prefix + Suffix
            return f"{random.choice(NFT_PREFIXES)}{random.choice(NFT_SUFFIXES)}".lower()
        elif combo == 2:
            # Single word + number
            return f"{random.choice(NFT_WORDS)}{random.choice(COOL_NUMBERS)}".lower()
        elif combo == 3:
            # Word_Word
            return f"{random.choice(NFT_WORDS)}_{random.choice(NFT_WORDS)}".lower()
        else:
            # Prefix + Suffix + number
            return f"{random.choice(NFT_PREFIXES)}{random.choice(NFT_SUFFIXES)}{random.choice(COOL_NUMBERS)}".lower()


def generate_unique_usernames(count: int = 10, style: str = "random") -> list[str]:
    """Generate a list of unique NFT-style usernames."""
    usernames = set()
    attempts = 0
    max_attempts = count * 10
    
    while len(usernames) < count and attempts < max_attempts:
        username = generate_nft_username(style)
        # Telegram usernames: 5-32 chars, alphanumeric + underscores
        if 5 <= len(username) <= 32 and all(c.isalnum() or c == '_' for c in username):
            usernames.add(username)
        attempts += 1
    
    return list(usernames)


async def check_username_availability(username: str) -> dict:
    """
    Check if a Telegram username is available.
    Returns: {"username": str, "available": bool, "reason": str}
    """
    try:
        from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError
        # Try to resolve the username - if it exists, it will return a user
        entity = await userbot.get_entity(username)
        return {
            "username": username,
            "available": False,
            "reason": f"Taken by @{entity.username or entity.id}"
        }
    except UsernameNotOccupiedError:
        # Username not found = available
        return {
            "username": username,
            "available": True,
            "reason": "Available!"
        }
    except UsernameInvalidError:
        return {
            "username": username,
            "available": False,
            "reason": "Invalid username format"
        }
    except Exception as e:
        return {
            "username": username,
            "available": False,
            "reason": f"Error: {str(e)}"
        }


async def find_available_usernames(count: int = 10, style: str = "random") -> list[dict]:
    """
    Generate and check availability of NFT-style usernames.
    Returns list of {"username": str, "available": bool, "reason": str}
    """
    usernames = generate_unique_usernames(count * 3, style)  # Generate extra to account for taken ones
    results = []
    
    # Check availability concurrently with semaphore
    sem = asyncio.Semaphore(5)  # Limit concurrent requests
    
    async def check_with_limit(uname):
        async with sem:
            return await check_username_availability(uname)
    
    tasks = [check_with_limit(u) for u in usernames]
    
    all_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    available_count = 0
    for result in all_results:
        if isinstance(result, dict):
            results.append(result)
            if result["available"]:
                available_count += 1
                if available_count >= count:
                    break
    
    return results


def extract_codes(text: str) -> list[str]:
    """Extract codes from message text."""
    codes = []
    for pattern in CODE_PATTERNS:
        for match in pattern.finditer(text):
            code = match.group(1).strip()
            if code.isdigit():
                continue
            if not any(c.isalpha() for c in code):
                continue
            if code not in claimed_codes and code not in codes:
                codes.append(code)
    return codes


# ---------------------------------------------------------------------------
# SSE — push codes to browser extension in real-time
# ---------------------------------------------------------------------------
sse_clients: list[web.StreamResponse] = []


async def handle_sse(request: web.Request) -> web.StreamResponse:
    """GET /api/stream — SSE endpoint, pushes codes as they arrive."""
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await response.prepare(request)
    sse_clients.append(response)
    log.info("SSE client connected (%d total)", len(sse_clients))

    try:
        # Send initial heartbeat
        await response.write(b"event: connected\ndata: ok\n\n")

        # Keep connection alive, wait for disconnect
        while True:
            await asyncio.sleep(10)
            await response.write(b": heartbeat\n\n")
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    finally:
        if response in sse_clients:
            sse_clients.remove(response)
            log.info("SSE client disconnected (%d total)", len(sse_clients))

    return response


async def push_code_to_sse(code: str, message: str = ""):
    """Broadcast a code to all connected SSE clients."""
    import json as _json
    data = _json.dumps({"code": code, "message": message})
    payload = f"event: code\ndata: {data}\n\n"
    dead = []
    for client in sse_clients:
        try:
            await client.write(payload.encode())
        except Exception:
            dead.append(client)
    for d in dead:
        sse_clients.remove(d)


async def start_http_server():
    """Start the HTTP API server on Railway's PORT."""
    app = web.Application()
    app.router.add_get("/api/stream", handle_sse)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/codes", handle_get_codes)
    app.router.add_post("/api/claimed", handle_claimed)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("HTTP API started on port %s", port)


async def handle_status(request: web.Request) -> web.Response:
    """GET /api/status — health check."""
    return web.json_response({
        "status": "ok",
        "claimed": len(claimed_codes),
    })


async def handle_get_codes(request: web.Request) -> web.Response:
    """GET /api/codes — returns unclaimed codes."""
    unclaimed = [c for c in pending_codes if c["code"] not in claimed_codes]
    return web.json_response(unclaimed)


async def handle_claimed(request: web.Request) -> web.Response:
    """POST /api/claimed — mark a code as claimed."""
    data = await request.json()
    code = data.get("code")
    if code:
        claimed_codes.add(code)
        log.info("Code marked as claimed: %s", code)
    return web.json_response({"ok": True})


# ---------------------------------------------------------------------------
# Bot commands — /start panel
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a panel with Add to Group and Add to Channel buttons."""
    bot_username = context.bot.username
    add_group_url = f"https://t.me/{bot_username}?startgroup=true"

    keyboard = [
        [InlineKeyboardButton("👥 Add to Group", url=add_group_url)],
        [InlineKeyboardButton("📢 How to Add to Channel", callback_data="help_channel")],
        [InlineKeyboardButton("🎲 Generate NFT Usernames", callback_data="gen_usernames")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🤖 **Telegram Forwarder Bot**\n\n"
        "I relay messages from a source group/channel to a destination group/channel.\n\n"
        "**Choose an option below:**\n"
        "• **Group** — tap the button to add me directly\n"
        "• **Channel** — I'll show you how to add me as admin\n"
        "• **NFT Usernames** — generate cool available usernames"
    )
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def cmd_gen_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate NFT-style usernames and check availability."""
    args = context.args
    count = 10
    style = "random"
    
    if args:
        try:
            count = min(int(args[0]), 20)  # Max 20
        except ValueError:
            pass
    if len(args) > 1:
        style = args[1].lower()
    
    await update.message.reply_text(f"🔍 Generating {count} {style} usernames and checking availability...")
    
    results = await find_available_usernames(count, style)
    
    available = [r for r in results if r["available"]]
    taken = [r for r in results if not r["available"]]
    
    if not available:
        text = "❌ No available usernames found. Try again or change style."
        await update.message.reply_text(text)
        return
    
    text_lines = [f"✅ **Found {len(available)} Available Usernames:**\n"]
    
    for i, r in enumerate(available[:10], 1):
        text_lines.append(f"{i}. @{r['username']}")
    
    if taken:
        text_lines.append(f"\n📊 *Checked {len(results)} | {len(available)} available | {len(taken)} taken*")
    
    text_lines.append("\n💡 *Copy any username and claim it fast!*")
    
    await update.message.reply_text("\n".join(text_lines), parse_mode="Markdown")


async def callback_gen_usernames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Generate NFT Usernames button."""
    query = update.callback_query
    await query.answer()
    
    # Simulate /gen command
    await query.edit_message_text("🔍 Generating 10 random usernames and checking availability...")
    
    results = await find_available_usernames(10, "random")
    
    available = [r for r in results if r["available"]]
    taken = [r for r in results if not r["available"]]
    
    if not available:
        text = "❌ No available usernames found. Try /gen again."
        await query.edit_message_text(text)
        return
    
    text_lines = [f"✅ **Found {len(available)} Available Usernames:**\n"]
    
    for i, r in enumerate(available[:10], 1):
        text_lines.append(f"{i}. @{r['username']}")
    
    if taken:
        text_lines.append(f"\n📊 *Checked {len(results)} | {len(available)} available | {len(taken)} taken*")
    
    text_lines.append("\n💡 *Copy any username and claim it fast!*")
    
    # Add back button
    keyboard = [[InlineKeyboardButton("🔄 Generate More", callback_data="gen_usernames")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("\n".join(text_lines), parse_mode="Markdown", reply_markup=reply_markup)


async def callback_help_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show instructions for adding bot to a channel."""
    query = update.callback_query
    await query.answer()

    text = (
        "📢 **How to Add Bot to a Channel:**\n\n"
        "1. Open your channel in Telegram\n"
        "2. Tap the channel name → **Administrators**\n"
        "3. Tap **Add Admin**\n"
        "4. Search for `@{bot}` and select it\n"
        "5. Enable **Post Messages** permission\n"
        "6. Tap **Save**\n\n"
        "Then set the channel ID as `DEST_GROUP_ID` in Railway."
    ).format(bot=context.bot.username)

    await query.edit_message_text(text, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# Relay logic
# ---------------------------------------------------------------------------
async def _do_relay(msg):
    """Actual send logic — runs as a background task."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = msg.text or ""

    if text:
        # Detect codes
        codes = extract_codes(text)
        for code in codes:
            entry = {
                "code": code,
                "message": text,
                "timestamp": timestamp,
                "msg_id": msg.id,
            }
            pending_codes.append(entry)
            log.info("CODE DETECTED: %s", code)
            if len(pending_codes) > MAX_PENDING:
                pending_codes.pop(0)
            # Push to browser extension instantly via SSE
            await push_code_to_sse(code, text)

        # If codes found, forward ONLY the code. Otherwise forward full message.
        if codes:
            forward_text = codes[0]
        else:
            forward_text = text

        try:
            await bot.send_message(chat_id=cfg["DEST_GROUP_ID"], text=forward_text)
            log.info("RELAY OK | src_msg_id=%s ts=%s codes=%s", msg.id, timestamp, codes)
        except Exception as exc:
            log.error("RELAY FAIL | src_msg_id=%s ts=%s error=%s", msg.id, timestamp, exc)

    if msg.photo:
        try:
            photo_file = await msg.download_media(file=bytes)
            await bot.send_photo(chat_id=cfg["DEST_GROUP_ID"], photo=photo_file, caption=msg.text or "")
            log.info("PHOTO RELAY OK | src_msg_id=%s ts=%s", msg.id, timestamp)
        except Exception as exc:
            log.error("PHOTO RELAY FAIL | src_msg_id=%s ts=%s error=%s", msg.id, timestamp, exc)
    elif msg.document:
        try:
            doc_file = await msg.download_media(file=bytes)
            filename = msg.file.name or "document"
            await bot.send_document(chat_id=cfg["DEST_GROUP_ID"], document=doc_file, filename=filename, caption=msg.text or "")
            log.info("DOC RELAY OK | src_msg_id=%s ts=%s file=%s", msg.id, timestamp, filename)
        except Exception as exc:
            log.error("DOC RELAY FAIL | src_msg_id=%s ts=%s error=%s", msg.id, timestamp, exc)


async def relay_message(event: events.NewMessage.Event):
    """Fire-and-forget relay — handler returns instantly, send runs in background."""
    asyncio.create_task(_do_relay(event.message))


# ---------------------------------------------------------------------------
# Main — reconnect loop
# ---------------------------------------------------------------------------
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds


async def main():
    log.info("Starting Telegram forwarder...")
    log.info("Source group: %s | Dest group: %s", cfg["SOURCE_GROUP_ID"], cfg["DEST_GROUP_ID"])

    # Start HTTP API server
    await start_http_server()

    # Start bot command handler
    app = Application.builder().token(cfg["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("gen", cmd_gen_usernames))
    app.add_handler(CommandHandler("usernames", cmd_gen_usernames))
    app.add_handler(CallbackQueryHandler(callback_help_channel, pattern="^help_channel$"))
    app.add_handler(CallbackQueryHandler(callback_gen_usernames, pattern="^gen_usernames$"))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    log.info("Bot polling started — /start command active")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if not userbot.is_connected():
                await userbot.start()
                log.info("Userbot connected as %s (attempt %s)", (await userbot.get_me()).first_name, attempt)

            userbot.add_event_handler(relay_message, events.NewMessage(chats=cfg["SOURCE_GROUP_ID"]))
            log.info("Listening for new messages in source group %s ...", cfg["SOURCE_GROUP_ID"])

            await userbot.run_until_disconnected()
            log.info("Userbot disconnected cleanly — exiting")
            break
        except Exception as exc:
            log.error("Attempt %s/%s failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                log.info("Retrying in %s seconds...", RETRY_DELAY)
                await asyncio.sleep(RETRY_DELAY)
            else:
                log.error("Max retries reached — exiting, Railway will restart")
                sys.exit(1)

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
