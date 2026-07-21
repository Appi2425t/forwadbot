# Telegram Group Forwarder

A stateless Telegram message relay that listens in a source group (via a userbot session) and forwards messages to a destination group (via a Bot API bot).

## Architecture

- **Userbot (Telethon)**: Joins the source group with your personal account, listens for new messages.
- **Bot (python-telegram-bot)**: Posts formatted messages into the destination group where it is a member.
- **Single process**: Both clients run concurrently in one asyncio loop on Railway.

## Prerequisites

1. **Telegram API credentials**: Go to [my.telegram.org](   ), create an app, note your `API_ID` and `API_HASH`.
2. **Bot token**: Create a bot via [@BotFather](https://t.me/BotFather), get the token, and add the bot to your destination group as a member (admin recommended).
3. **Group IDs**: You need the numeric IDs for both source and destination groups. You can get these by forwarding a message from the group to [@userinfobot](https://t.me/userinfobot) or using the Telegram API.

## Step 1: Generate Session String (Local)

Run this **once** on your local machine (not on Railway):

```bash
pip install telethon
python generate_session.py
```

It will prompt for your phone number and the OTP you receive via Telegram. It then prints a session string — copy it.

## Step 2: Set Environment Variables in Railway

**Option A — Raw Editor (easiest):**

1. In Railway dashboard, go to your service → **Variables** tab.
2. Click **Raw Editor**.
3. Paste this and fill in your values:

```
API_ID=your_api_id
API_HASH=your_api_hash
SESSION_STRING=your_session_string
SOURCE_GROUP_ID=-1001234567890
BOT_TOKEN=your_bot_token
DEST_GROUP_ID=-1001234567891
```

4. Click Save.

**Option B — Railway CLI script:**

```bash
pip install -r requirements.txt
python setup_railway_vars.py
```

It will prompt for each value and set them via `railway variables set`.

> Group IDs are negative numbers (e.g. `-1001234567890`). For supergroups, they typically start with `-100`.

## Step 3: Deploy

### Option A: Railway CLI
```bash
railway up
```

### Option B: GitHub Auto-Deploy
1. Push this repo to GitHub.
2. In Railway, link the repo and enable auto-deploy on the `main` branch.

## Message Format

Each relayed message is prefixed with the sender's identity:

```
Alice: Hello, this is a forwarded message!
```

For photos and documents, the sender name appears as the caption.

## Logs

Every relay is logged to stdout with source message ID, timestamp, and success/fail status. View logs in the Railway dashboard under the service's **Deployments** tab.

## How It Works

1. Telethon connects using your `SESSION_STRING` (no interactive login needed).
2. It listens for `NewMessage` events in `SOURCE_GROUP_ID`.
3. Each message is formatted with the sender's display name.
4. The Bot API bot sends the formatted message to `DEST_GROUP_ID`.
5. On disconnect, the process exits and Railway restarts it (up to 10 retries).
