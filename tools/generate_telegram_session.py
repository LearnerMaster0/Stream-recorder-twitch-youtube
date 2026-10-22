#!/usr/bin/env python3
"""Create a Telethon StringSession for a private deployment environment.

Run locally on a trusted device. Never commit or share the printed session string.
"""
import asyncio
import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession


async def main() -> None:
    print("Telegram StringSession generator")
    print("Run this only on a device you trust. Do not send the result to anyone.")
    api_id = int(input("Telegram API ID: ").strip())
    api_hash = getpass.getpass("Telegram API HASH (input hidden): ").strip()
    if not api_hash:
        raise SystemExit("API HASH cannot be empty.")

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            phone = input("Telegram phone number with country code (e.g. +91...): ").strip()
            sent = await client.send_code_request(phone)
            code = getpass.getpass("Telegram login code (input hidden): ").strip()
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                password = getpass.getpass("Telegram two-step verification password (input hidden): ")
                await client.sign_in(password=password)

        me = await client.get_me()
        session = client.session.save()
        if not session:
            raise SystemExit("No session string was created.")

        print("\nTelegram account authorized.")
        print(f"Your numeric Telegram user ID (use for TELEGRAM_ALLOWED_USER_IDS): {me.id}")
        print("\nSESSION STRING (secret; copy directly into Voroa's secret environment variable):")
        print(session)
        print("\nDo not paste this into ChatGPT, GitHub files, issues, screenshots, or public chats.")
        print("If it is exposed, revoke the session from Telegram Settings > Devices.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
