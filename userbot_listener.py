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
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🤖 **Telegram Forwarder Bot**\n\n"
        "I relay messages from a source group/channel to a destination group/channel.\n\n"
        "**Choose an option below:**\n"
        "• **Group** — tap the button to add me directly\n"
        "• **Channel** — I'll show you how to add me as admin"
    )
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


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
    app.add_handler(CallbackQueryHandler(callback_help_channel, pattern="^help_channel$"))

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
