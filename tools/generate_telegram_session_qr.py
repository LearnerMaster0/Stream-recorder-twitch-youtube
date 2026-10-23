#!/usr/bin/env python3
"""Create a Telethon StringSession using Telegram QR login instead of an SMS/code flow.

Run only on a trusted device. Never share the printed StringSession.
"""
import asyncio
import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession


async def main():
    try:
        api_id = int(input("Telegram API ID: ").strip())
    except ValueError:
        raise SystemExit("API ID must be a number.")

    api_hash = getpass.getpass("Telegram API HASH (hidden): ").strip()
    if not api_hash:
        raise SystemExit("API HASH cannot be empty.")

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            try:
                import qrcode
            except ImportError:
                raise SystemExit(
                    "Missing QR display package. Run: python -m pip install qrcode"
                )

            qr_login = await client.qr_login()
            print("\nScan this QR from the Telegram account you want to connect.")
            print("Telegram app: Settings > Devices > Link Desktop Device.")
            print("If scanning on the same phone, take a screenshot and use the scanner's gallery option if available.\n")
            qr = qrcode.QRCode(border=2)
            qr.add_data(qr_login.url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)

            try:
                await qr_login.wait()
            except SessionPasswordNeededError:
                password = getpass.getpass(
                    "Telegram 2-Step Verification password (hidden): "
                )
                await client.sign_in(password=password)

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
