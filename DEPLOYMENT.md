# Deployment and storage notes

This application is a long-running background worker. It records media to disk, processes/splits files, stores recovery state in SQLite, and uses a Telethon session file. It is not a static website.

## Required runtime

- Python 3.10 or 3.11
- `ffmpeg` and `ffprobe`
- GPAC `MP4Box` (used by the splitter)
- Dependencies from `requirements.txt`
- A persistent filesystem with enough free space for the source recording plus temporary and split copies
- Persistent storage for `recordings/`, `temp/`, `data/`, `logs/`, and the Telethon `.session` file

## Basic Linux setup

1. Install Python, pip, FFmpeg/FFprobe, and GPAC/MP4Box using packages appropriate for your Linux distribution. GPAC installation instructions: https://gpac.io/downloads/gpac-nightly-builds/
2. Clone the repository and enter its directory.
3. Create a virtual environment and install dependencies:

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Copy `config.yaml.example` to `config.yaml` and enter your own Telegram/platform settings. Keep `config.yaml`, `cookies.txt`, and Telethon session files private; never commit them.
5. Ensure the configured output, temporary, data, and log directories are on persistent storage.
6. Start the worker with `python main.py`. First-time Telegram login may ask for a code and, if enabled, a two-step verification password.

## Telegram private-chat YouTube link mode

The worker accepts YouTube links sent in a private chat to the Telegram account used by Telethon. Requests are stored in `data/link_requests.sqlite3` and processed one at a time. After recording, the worker replies in that same private chat and sends the video there; it does not publish the recording to the configured channel. Files larger than the account's upload target are split only when required.

Set these Voroa Environment variables:

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_CHANNEL_ID` (the current config loader still requires the channel ID for compatibility, even though manual-link deliveries go to private chats).
- `TELEGRAM_SESSION_STRING`: a Telethon StringSession generated securely for the account that should receive the links and send the files. Without this, a headless worker may fail because first-time login needs an interactive code.
- `TELEGRAM_ALLOWED_USER_IDS`: the owner's numeric Telegram user ID. Only IDs in this comma-separated allowlist may submit links. The listener rejects requests until this variable is set.
- `YOUTUBE_CHANNELS` is optional in link mode. Leave it blank if you only want to send individual links in Telegram.

For YouTube live links, the recorder passes yt-dlp's `--live-from-start` option: if you send a link 30 minutes after the live began, it attempts to fetch the available stream from time 0 and catch up toward the live edge while continuing the capture. The completed recording is only delivered after yt-dlp exits and the output is finalized. If YouTube rejects the start-from-beginning request with HTTP 403, the recorder now marks that request as failed instead of silently retrying from the current live edge and delivering a video missing the beginning.

The queue survives worker restarts, but a recording interrupted by a host restart may be attempted again from its URL and can create a new output file. Catch-up from time 0 is possible only when YouTube/yt-dlp actually exposes the beginning of that stream; this cannot be guaranteed for every livestream, and must be verified with a real delayed-link test. A Telethon user session is used by this project; it is not a Bot API token session.

## Android/mobile-only workflow

A phone browser can edit the repository, configure a host, and monitor GitHub Actions, but GitHub Actions is not a suitable always-on recorder: workflow jobs are time-limited and their temporary disks are not durable recording storage.

Running directly on Android through Termux may be possible for experiments, but it is not the recommended production setup for unattended 3–5 hour recordings. Android may suspend background processes, battery optimization can stop work, mobile storage can fill, and the splitter requires a working `MP4Box` binary as well as FFmpeg. Before relying on a Termux setup, verify that Python dependencies and both media tools are installable for the phone's CPU/Android version and test a short stream while the screen is off.

The most practical mobile-only operating model is: configure and deploy from the phone browser, run the worker on a persistent remote Linux VM/worker with attached storage, and control/check it through Telegram. The worker still needs its own Telegram login session created securely; never paste API hashes, session files, or two-step passwords into public issues or commits.

## Free-hosting limitations

Do not rely on a free static-site or short-lived serverless host for 3–5 hour recordings. The process must remain alive and the local filesystem must survive restarts.

- Render's free web services sleep after 15 minutes without inbound traffic and use an ephemeral filesystem: https://render.com/docs/free
- Railway's current Free plan provides $1/month in usage credit and 0.5 GB of volume storage after the trial: https://docs.railway.com/pricing/plans and https://docs.railway.com/volumes/reference

Those limits are not suitable for multi-hour video files and durable recovery state. A persistent VM or always-on worker with attached storage is the safer choice. Check provider pricing and limits before deploying; do not assume continuous hosting or large disk space is free.

## Operational safety

- Start with a short test stream before relying on a production recording.
- Keep enough disk space for the original recording and temporary copies during splitting/remuxing.
- Back up the SQLite state and Telethon session securely; never publish the session file.
- CI unit tests do not prove that a real live stream and Telegram upload will succeed end to end.
