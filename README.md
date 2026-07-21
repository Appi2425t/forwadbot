# Telegram Group Forwarder

A stateless Telegram message relay that listens in a source group (via a userbot session) and forwards messages to a destination group (via a Bot API bot).

## Architecture

- **Userbot (Telethon)**: Joins the source group with your personal account, listens for new messages.
- **Bot (python-telegram-bot)**: Posts formatted messages into the destination group where it is a member.
- **Single process**: Both clients run concurrently in one asyncio loop on Railway.

## Prerequisites

1. **Telegram API credentials**: Go to [my.telegram.org](https://my.telegram.org), create an app, note your `API_ID` and `API_HASH`.
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

In your Railway project dashboard, go to the **Variables** tab and add:

| Variable | Description |
|---|---|
| `API_ID` | From my.telegram.org |
| `API_HASH` | From my.telegram.org |
| `SESSION_STRING` | Output from `generate_session.py` |
| `SOURCE_GROUP_ID` | Numeric ID of the group to listen in |
| `BOT_TOKEN` | From @BotFather |
| `DEST_GROUP_ID` | Numeric ID of the group to post into |

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
