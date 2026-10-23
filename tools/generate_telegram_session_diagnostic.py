#!/usr/bin/env python3
"""One-attempt Telethon login helper with clearer code-delivery diagnostics.

Run only on a trusted device. Never share the printed StringSession.
This intentionally requests a login code only once per run.
"""
import asyncio
import getpass

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession


def describe_delivery(sent):
    code_type = type(getattr(sent, "type", None)).__name__
    next_type = type(getattr(sent, "next_type", None)).__name__
    print("\nTelegram accepted the code request.")
    print(f"Delivery method reported by Telegram: {code_type}")
    if next_type != "NoneType":
        print(f"Possible next delivery method: {next_type}")
    print("Check the official Telegram service chat on an already logged-in device.")
    print("The login code will NOT appear inside this Termux terminal.")
    print("Enter only the newest code for this exact request.")
    print("If no code arrives, stop here; do not repeatedly request codes.")


async def main():
    print("Telegram Session String helper (single code request)")
    print("Keep API credentials and the resulting session string private.")
    try:
        api_id = int(input("Telegram API ID: ").strip())
    except ValueError:
        raise SystemExit("API ID must be a number.")

    api_hash = getpass.getpass("Telegram API HASH (hidden): ").strip()
    if not api_hash:
        raise SystemExit("API HASH cannot be empty.")

    phone = input("Telegram phone number with country code (e.g. +91...): ").strip()
    if not phone:
        raise SystemExit("Phone number cannot be empty.")

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"Already authorized as Telegram user ID: {me.id}")
        else:
            try:
                sent = await client.send_code_request(phone)
            except FloodWaitError as exc:
                raise SystemExit(
                    f"Telegram asked you to wait {exc.seconds} seconds. "
                    "Do not retry until that time has passed."
                )
            describe_delivery(sent)
            code = input("Paste/type the newest Telegram login code here: ").strip().replace(" ", "")
            if not code:
                raise SystemExit("No code entered. No further code request was made.")
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                password = getpass.getpass("Telegram 2-Step Verification password (hidden): ")
                await client.sign_in(password=password)
            except PhoneCodeInvalidError:
                raise SystemExit(
                    "Telegram rejected this code. Stop; do not request codes repeatedly. "
                    "Make sure it is the newest code sent for this exact attempt."
                )
            except PhoneCodeExpiredError:
                raise SystemExit(
                    "This code expired. Stop for now and wait before attempting again."
                )

        me = await client.get_me()
        session = client.session.save()
        if not session:
            raise SystemExit("No session string was created.")
        print("\nAuthorized successfully.")
        print(f"Telegram user ID (for TELEGRAM_ALLOWED_USER_IDS): {me.id}")
        print("\nSESSION STRING (secret; paste directly into Voroa's secret environment variable):")
        print(session)
        print("\nNever paste the session string into ChatGPT, GitHub, screenshots, or public chats.")
        print("If exposed, revoke the session in Telegram Settings > Devices.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
