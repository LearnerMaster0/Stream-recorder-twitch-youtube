#!/usr/bin/env python3
"""Create a Telethon StringSession using login-code authentication.

Run on a trusted device only. Never share the printed session string.
"""
import asyncio
import getpass

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyNotFound,
    AuthKeyUnregisteredError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession


async def main() -> None:
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

    # Start with a fresh client/auth key for each attempt. Reusing a client
    # after a broken mobile connection can leave the QR/code flow with a stale key.
    for attempt in range(1, 4):
        client = TelegramClient(
            StringSession(),
            api_id,
            api_hash,
            connection_retries=2,
            request_retries=2,
            auto_reconnect=True,
            timeout=30,
        )
        try:
            print(f"\nConnection attempt {attempt}/3...")
            await asyncio.wait_for(client.connect(), timeout=35)

            if not await client.is_user_authorized():
                sent = await client.send_code_request(phone)
                print("Login code requested. Check Telegram app messages first; SMS may not be used.")
                code = getpass.getpass("Telegram login code (hidden): ").strip()
                try:
                    await client.sign_in(
                        phone=phone,
                        code=code,
                        phone_code_hash=sent.phone_code_hash,
                    )
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
            print("\nNever paste this session string into ChatGPT, GitHub, screenshots, or public chats.")
            print("If exposed, revoke the session in Telegram Settings > Devices.")
            return

        except (PhoneCodeInvalidError, PhoneCodeExpiredError) as exc:
            raise SystemExit(
                f"{type(exc).__name__}: Telegram rejected or expired that code. "
                "Run the script again and enter the newest code."
            )
        except (AuthKeyNotFound, OSError, asyncio.TimeoutError, ConnectionError) as exc:
            print(f"Connection/auth-key error: {type(exc).__name__}.")
            if attempt == 3:
                raise SystemExit(
                    "Telegram connection failed 3 times. No session was created. "
                    "Try a different internet connection later; do not keep retrying repeatedly."
                )
            print("Discarding this client and creating a fresh connection...")
        except Exception as exc:
            message = str(exc)
            if "auth key" in message.lower() and "expir" in message.lower() and attempt < 3:
                print("Telegram says the auth key expired. Creating a completely fresh client...")
                continue
            raise
        finally:
            if client.is_connected():
                await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
