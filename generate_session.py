"""
One-off local utility to generate a Telethon StringSession.
Run this INTERACTIVELY on your local machine (not on Railway).
It will prompt for your phone number and the OTP you receive.

Usage:
    pip install telethon
    python generate_session.py

The printed string is your SESSION_STRING — paste it into Railway env vars.
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(input("Enter your Telegram API ID (from my.telegram.org): "))
API_HASH = input("Enter your Telegram API hash: ").strip()


async def main():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        print("\nSession string (copy this into Railway as SESSION_STRING):\n")
        print(client.session.save())
        print()


asyncio.run(main())
