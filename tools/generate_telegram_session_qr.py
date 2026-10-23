#!/usr/bin/env python3
"""Create a Telethon StringSession using Telegram QR login instead of a code flow.

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

    client = TelegramClient(
        StringSession(), api_id, api_hash,
        connection_retries=3, request_retries=3, auto_reconnect=True,
    )
    try:
        await client.connect()
        if not await client.is_user_authorized():
            try:
                import qrcode
            except ImportError:
                raise SystemExit(
                    "Missing QR package. Run: python -m pip install qrcode"
                )

            print("\nKeep this screen open. In Telegram, open Settings > Devices > Link Desktop Device.")
            print("Scan each QR promptly; it expires and will refresh automatically.")
            print("If the connection drops repeatedly, switch network (Wi-Fi/mobile data) and retry.\n")

            authorized = False
            for attempt in range(1, 4):
                if not client.is_connected():
                    await client.connect()
                qr_login = await client.qr_login()
                print(f"\nQR attempt {attempt}/3:")
                qr = qrcode.QRCode(border=2)
                qr.add_data(qr_login.url)
                qr.make(fit=True)
                qr.print_ascii(invert=True)
                try:
                    await qr_login.wait(timeout=120)
                    authorized = True
                    break
                except asyncio.TimeoutError:
                    print("\nQR expired before approval. Generating a fresh QR...")
                except SessionPasswordNeededError:
                    password = getpass.getpass(
                        "Telegram 2-Step Verification password (hidden): "
                    )
                    await client.sign_in(password=password)
                    authorized = True
                    break

            if not authorized and not await client.is_user_authorized():
                raise SystemExit(
                    "QR login timed out 3 times. No session was created. "
                    "Check network, then try again later; do not repeatedly retry."
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
    except (OSError, asyncio.TimeoutError) as exc:
        raise SystemExit(
            f"Network/connection problem: {type(exc).__name__}. "
            "Check your internet connection and try later."
        )
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
