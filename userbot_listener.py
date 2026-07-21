"""
Telegram Forwarding Tool — Userbot Listener + Bot API Relayer
Single asyncio process: Telethon client listens, python-telegram-bot relays.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Bot

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
# Relay logic
# ---------------------------------------------------------------------------
async def relay_message(event: events.NewMessage.Event):
    """Forward a new message from SOURCE_GROUP to DEST_GROUP via the bot."""
    msg = event.message
    sender = await event.get_sender()

    # Build sender identity string
    if sender is None:
        sender_name = "Unknown"
    elif getattr(sender, "first_name", None):
        sender_name = sender.first_name
        if getattr(sender, "last_name", None):
            sender_name += " " + sender.last_name
    elif getattr(sender, "username", None):
        sender_name = f"@{sender.username}"
    else:
        sender_name = "Unknown"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = msg.text or ""

    if text:
        formatted = f"**{sender_name}**: {text}"
        try:
            await bot.send_message(chat_id=cfg["DEST_GROUP_ID"], text=formatted, parse_mode="Markdown")
            log.info("RELAY OK | src_msg_id=%s ts=%s sender=%s", msg.id, timestamp, sender_name)
        except Exception as exc:
            log.error("RELAY FAIL | src_msg_id=%s ts=%s sender=%s error=%s", msg.id, timestamp, sender_name, exc)

    # Stretch goal: photos
    if msg.photo:
        try:
            photo_file = await msg.download_media(file=bytes)
            caption = f"**{sender_name}**: {msg.text or ''}" if msg.text else f"**{sender_name}**"
            await bot.send_photo(chat_id=cfg["DEST_GROUP_ID"], photo=photo_file, caption=caption, parse_mode="Markdown")
            log.info("PHOTO RELAY OK | src_msg_id=%s ts=%s sender=%s", msg.id, timestamp, sender_name)
        except Exception as exc:
            log.error("PHOTO RELAY FAIL | src_msg_id=%s ts=%s sender=%s error=%s", msg.id, timestamp, sender_name, exc)

    # Stretch goal: documents (non-photo files)
    elif msg.document:
        try:
            doc_file = await msg.download_media(file=bytes)
            filename = msg.file.name or "document"
            caption = f"**{sender_name}**: {msg.text or ''}" if msg.text else f"**{sender_name}**"
            await bot.send_document(chat_id=cfg["DEST_GROUP_ID"], document=doc_file, filename=filename, caption=caption, parse_mode="Markdown")
            log.info("DOC RELAY OK | src_msg_id=%s ts=%s sender=%s file=%s", msg.id, timestamp, sender_name, filename)
        except Exception as exc:
            log.error("DOC RELAY FAIL | src_msg_id=%s ts=%s sender=%s error=%s", msg.id, timestamp, sender_name, exc)


# ---------------------------------------------------------------------------
# Main — reconnect loop
# ---------------------------------------------------------------------------
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds


async def main():
    log.info("Starting Telegram forwarder...")
    log.info("Source group: %s | Dest group: %s", cfg["SOURCE_GROUP_ID"], cfg["DEST_GROUP_ID"])

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if not userbot.is_connected():
                await userbot.start()
                log.info("Userbot connected as %s (attempt %s)", (await userbot.get_me()).first_name, attempt)

            userbot.add_event_handler(relay_message, events.NewMessage(chats=cfg["SOURCE_GROUP_ID"]))
            log.info("Listening for new messages in source group %s ...", cfg["SOURCE_GROUP_ID"])

            await userbot.run_until_disconnected()
            log.info("Userbot disconnected cleanly — exiting")
            return
        except Exception as exc:
            log.error("Attempt %s/%s failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                log.info("Retrying in %s seconds...", RETRY_DELAY)
                await asyncio.sleep(RETRY_DELAY)
            else:
                log.error("Max retries reached — exiting, Railway will restart")
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
