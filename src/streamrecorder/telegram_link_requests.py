"""Private Telegram DM intake for recording user-submitted YouTube URLs.

Requests are persisted in SQLite and processed sequentially. Pending requests
survive worker restarts; an interrupted recording is re-queued on next startup.
"""
import asyncio
import os
from contextlib import contextmanager
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logger import get_logger
from .stream_monitor import StreamInfo
from .splitter import FileSplitter

YOUTUBE_URL_RE = re.compile(
    r"https?://(?:(?:www|m)\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|live/|shorts/|embed/)|youtu\.be/)[^\s<>.,!?;]+",
    re.IGNORECASE,
)


class TelegramLinkRequestHandler:
    """Accept YouTube links in private Telegram chats and reply with recordings."""

    def __init__(self, client, recorder, uploader, splitting_config, cookies_file: str = ""):
        self.client = client
        self.recorder = recorder
        self.uploader = uploader
        self.splitting_config = splitting_config
        self.cookies_file = cookies_file
        self.logger = get_logger("telegram_link_requests")
        self.db_path = Path(os.environ.get("LINK_REQUESTS_DB", "./data/link_requests.sqlite3"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._handler = None
        self._worker: Optional[asyncio.Task] = None
        self._wake_worker = asyncio.Event()
        self._stopped = False
        raw_ids = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").strip()
        self.allowed_user_ids = {
            int(value.strip()) for value in raw_ids.split(",") if value.strip().isdigit()
        }

    def _connect_db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute(
            """CREATE TABLE IF NOT EXISTS link_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT
            )"""
        )
        db.commit()
        return db

    @contextmanager
    def _db(self):
        connection = self._connect_db()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def start(self) -> None:
        if self._handler is not None:
            return
        with self._db() as db:
            # If the process died during recording, retry the request after restart.
            db.execute(
                "UPDATE link_requests SET status='queued', updated_at=? WHERE status='recording'",
                (datetime.now().isoformat(),),
            )
        from telethon import events
        self._handler = self._on_message
        self.client.add_event_handler(self._handler, events.NewMessage(incoming=True))
        self._worker = asyncio.create_task(self._work_queue(), name="youtube-link-recording-queue")
        self._wake_worker.set()
        self.logger.info("Private Telegram YouTube-link intake started (SQLite queue)")

    async def stop(self) -> None:
        self._stopped = True
        if self._handler is not None:
            from telethon import events
            self.client.remove_event_handler(self._handler, events.NewMessage)
            self._handler = None
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def _on_message(self, event) -> None:
        try:
            if not event.is_private:
                return
            sender_id = int(getattr(event, "sender_id", 0) or 0)
            if not sender_id:
                return
            text = (event.raw_text or "").strip()
            match = YOUTUBE_URL_RE.search(text)
            if not match:
                return
            url = match.group(0).rstrip(".,!?;")
            if not self.allowed_user_ids:
                await event.reply(
                    "⚙️ सुरक्षित सेटअप अधूरा है। मालिक का Telegram numeric ID "
                    "Voroa में TELEGRAM_ALLOWED_USER_IDS नाम के Environment variable में जोड़ें।"
                )
                return
            if sender_id not in self.allowed_user_ids:
                await event.reply("⛔ इस बॉट से रिकॉर्डिंग माँगने की अनुमति नहीं है।")
                return
            with self._db() as db:
                duplicate = db.execute(
                    "SELECT id FROM link_requests WHERE sender_id=? AND url=? "
                    "AND status IN ('queued','recording')",
                    (sender_id, url),
                ).fetchone()
                if duplicate:
                    await event.reply(f"ℹ️ यह लिंक पहले से कतार में है (रिक्वेस्ट #{duplicate['id']})।")
                    return
                cursor = db.execute(
                    "INSERT INTO link_requests(sender_id,url,status,created_at,updated_at) "
                    "VALUES(?,?,'queued',?,?)",
                    (sender_id, url, datetime.now().isoformat(), datetime.now().isoformat()),
                )
                request_id = cursor.lastrowid
                position = db.execute(
                    "SELECT COUNT(*) FROM link_requests WHERE status IN ('queued','recording')"
                ).fetchone()[0]
            await event.reply(
                f"✅ रिक्वेस्ट #{request_id} सुरक्षित कतार में जोड़ दी गई।\n"
                f"कतार में कुल सक्रिय/बाकी रिक्वेस्ट: {position}\n"
                "रिकॉर्डिंग पूरी होने पर वीडियो इसी प्राइवेट चैट में भेजी जाएगी।"
            )
            self._wake_worker.set()
        except Exception:
            self.logger.exception("Failed to accept Telegram link request")

    async def _work_queue(self) -> None:
        while True:
            try:
                request = None
                with self._db() as db:
                    request = db.execute(
                        "SELECT id,sender_id,url FROM link_requests WHERE status='queued' "
                        "ORDER BY id LIMIT 1"
                    ).fetchone()
                    if request:
                        db.execute(
                            "UPDATE link_requests SET status='recording',updated_at=? WHERE id=?",
                            (datetime.now().isoformat(), request["id"]),
                        )
                if request is None:
                    self._wake_worker.clear()
                    try:
                        await asyncio.wait_for(self._wake_worker.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
                    continue

                try:
                    await self._record_and_deliver(int(request["sender_id"]), request["url"])
                    status, error = "done", None
                except asyncio.CancelledError:
                    with self._db() as db:
                        db.execute(
                            "UPDATE link_requests SET status='queued',updated_at=? WHERE id=?",
                            (datetime.now().isoformat(), request["id"]),
                        )
                    raise
                except Exception as exc:
                    self.logger.exception("Recording request failed")
                    status, error = "failed", str(exc)[:1000]
                    try:
                        detail = str(exc).strip()[:500] or "अज्ञात त्रुटि"
                        await self.client.send_message(
                            int(request["sender_id"]),
                            f"❌ रिक्वेस्ट पूरी नहीं हो सकी: {detail}",
                        )
                    except Exception:
                        pass
                with self._db() as db:
                    db.execute(
                        "UPDATE link_requests SET status=?,error=?,updated_at=? WHERE id=?",
                        (status, error, datetime.now().isoformat(), request["id"]),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Queue worker iteration failed")
                await asyncio.sleep(3)

    async def _record_and_deliver(self, sender_id: int, url: str) -> None:
        video_id = url.split("?", 1)[-1].split("&", 1)[0] if "watch?" in url else url.rstrip("/").rsplit("/", 1)[-1]
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", video_id)[:24] or "youtube"
        channel = f"ytlink_{safe_id}"
        info = StreamInfo(
            channel=channel,
            title=f"YouTube recording {safe_id}",
            category="YouTube Live",
            started_at=datetime.now(),
            stream_url=url,
            is_live=True,
            output_ext="mp4",
        )
        await self.client.send_message(
            sender_id,
            "🔴 रिकॉर्डिंग शुरू हो रही है। लाइव स्ट्रीम खत्म होने तक प्रक्रिया चल सकती है।",
        )
        result = await self.recorder.record_stream(info, live_from_start=True)
        if result.status.value != "completed" or not result.output_path or not Path(result.output_path).is_file():
            reason = result.error or result.status.value
            raise RuntimeError(f"Recording did not complete: {reason}")

        output = Path(result.output_path)
        max_gb = (
            self.splitting_config.premium_size_gb
            if self.uploader.is_premium
            else self.splitting_config.default_size_gb
        )
        files = [str(output)]
        if output.stat().st_size > max_gb * 1024 * 1024 * 1024:
            splitter = FileSplitter(output_dir=str(output.parent))
            split_result = await splitter.split_file(
                str(output), max_gb, output_prefix=f"{output.stem}_part"
            )
            if not split_result.success or not split_result.output_files:
                raise RuntimeError(
                    "वीडियो Telegram सीमा से बड़ी थी और उसे बाँटना विफल हुआ; "
                    "रिकॉर्डिंग सर्वर पर सुरक्षित रखी गई है।"
                )
            files = split_result.output_files

        await self.client.send_message(
            sender_id,
            f"📤 रिकॉर्डिंग पूरी हुई ({len(files)} फ़ाइल)। अब इसी चैट में भेज रहा हूँ…",
        )
        total = len(files)
        for index, file_path in enumerate(files, start=1):
            caption = (
                f"🎬 YouTube Live recording\n🔗 {url}\n📦 Part {index}/{total}"
                if total > 1
                else f"🎬 YouTube Live recording\n🔗 {url}"
            )
            upload = await self.uploader.upload_file(
                file_path, caption, target_channel_id=sender_id
            )
            if not upload.success:
                raise RuntimeError(
                    f"Telegram पर फ़ाइल {index}/{total} भेजने में विफल: "
                    f"{upload.error or 'अज्ञात त्रुटि'}; "
                    f"फ़ाइल सर्वर पर रखी गई है: {Path(file_path).name}"
                )
        await self.client.send_message(sender_id, "✅ रिकॉर्डिंग की सभी फ़ाइलें भेज दी गई हैं।")

        # Release disk space only after every upload succeeds. On any upload failure,
        # the original and generated parts remain available for manual retry.
        cleanup_paths = set(files)
        cleanup_paths.add(str(output))
        for path in cleanup_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError as exc:
                self.logger.warning("Could not remove uploaded recording %s: %s", path, exc)
