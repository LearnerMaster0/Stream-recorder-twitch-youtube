# Android-only setup: create the Telegram session

This guide uses an Android phone to create the Telegram session required by the remote Voroa worker. The phone does not need to stay on during recording; the deployed worker performs recording and uploading.

## 1. Install Termux

Install Termux from its official F-Droid page: https://f-droid.org/packages/com.termux/

Avoid random APK download sites. Open Termux after installation.

## 2. Install Python and Git

Copy and run these commands one at a time in Termux:

```sh
pkg update
pkg upgrade
pkg install python git
```

If Termux asks for confirmation, read the prompt and type `y` when you want to continue.

## 3. Download the project branch

```sh
git clone -b test/codex-connector-access https://github.com/LearnerMaster0/Stream-recorder-twitch-youtube.git
cd Stream-recorder-twitch-youtube
python -m pip install --upgrade pip
python -m pip install 'telethon>=1.36.0'
```

## 4. Create the Telegram session

Run:

```sh
python tools/generate_telegram_session.py
```

The script asks for the Telegram API ID, API HASH, phone number, login code, and optional two-step verification password. The API hash, login code, and password are entered with hidden input. Use the API ID/API HASH from your own Telegram API application at https://my.telegram.org.

At the end it prints two things:
- Your numeric Telegram user ID. This value goes into Voroa's `TELEGRAM_ALLOWED_USER_IDS` environment variable.
- A long session string. This is secret account access; put it directly into Voroa's `TELEGRAM_SESSION_STRING` secret environment variable.

**Never paste the session string into ChatGPT, GitHub, screenshots, or any public chat.** Do not commit it to the repository. If you accidentally expose it, revoke that session from Telegram Settings → Devices.

## 5. Add the values in Voroa

Open the worker's Environment page:
https://app.getvoroa.com/worker/9hpqyuniscmssdbae6r8jqld/environment

Add or update:
- `TELEGRAM_SESSION_STRING` = the generated secret session string
- `TELEGRAM_ALLOWED_USER_IDS` = your numeric Telegram user ID

Do not delete the existing `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, or `TELEGRAM_CHANNEL_ID` values. Save the environment and redeploy/restart the worker if the host asks for it.

## 6. Verify from Telegram

After deployment, open the same Telegram account that the session belongs to and send a YouTube Live URL to that account's private chat. Only IDs listed in `TELEGRAM_ALLOWED_USER_IDS` are allowed. Check the Voroa logs if no acknowledgement arrives.

Start with a short test before trusting a multi-hour recording. GitHub unit tests are not an end-to-end recording test. A delayed YouTube link can only start at 0:00 if YouTube/yt-dlp exposes the beginning of that live stream.

## Important

- The remote worker needs persistent storage for recordings, temporary files, SQLite queue/state, and session data.
- The phone can be turned off after deployment; the remote worker must remain running.
- This helper creates a Telethon **user session**, not a Bot API bot-token session.
