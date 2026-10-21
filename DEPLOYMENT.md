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
