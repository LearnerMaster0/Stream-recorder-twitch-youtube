"""Private Telegram DM intake for recording user-submitted YouTube URLs.

This listener runs on the existing Telethon session. Requests are serialized in
one in-memory queue so only one manual recording runs at a time.
"""
import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logger import get_logger
from .stream_monitor import StreamInfo
from .splitter import FileSplitter

YOUTUBE_URL_RE = re.compile(
    r"https?://(?:(?:www|m)\.)?(?:youtube\.com/(?:watch\\?[^\s]*v=|live/|shorts/|embed/)|youtu\.be/)[^\s<>]+",
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
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=20)
        self._handler = None
        self._worker: Optional[asyncio.Task] = None
        self._stopped = False
        raw_ids = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").strip()
        self.allowed_user_ids = {
            int(value.strip()) for value in raw_ids.split(",") if value.strip().isdigit()
        }

    async def start(self) -> None:
        if self._handler is not None:
            return
        from telethon import events
        self._handler = self._on_message
        self.client.add_event_handler(self._handler, events.NewMessage(incoming=True))
        self._worker = asyncio.create_task(self._work_queue(), name="youtube-link-recording-queue")
        self.logger.info("Private Telegram YouTube-link intake started")

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
            url = match.group(0).rstrip(".,);]}")
            if self.allowed_user_ids and sender_id not in self.allowed_user_ids:
                await event.reply("⛔ इस बॉट से रिकॉर्डिंग माँगने की अनुमति नहीं है।")
                return
            if self.queue.full():
                await event.reply("⌛ रिकॉर्डिंग कतार अभी भरी है। थोड़ी देर बाद फिर भेजें।")
                return
            await self.queue.put((sender_id, url, event))
            position = self.queue.qsize()
            await event.reply(
                "✅ YouTube लिंक कतार में जोड़ दिया गया है।\n"
                f"कतार में आपकी स्थिति: {position}\n"
                "रिकॉर्डिंग पूरी होने पर वीडियो इसी प्राइवेट चैट में भेजी जाएगी।"
            )
        except Exception:
            self.logger.exception("Failed to accept Telegram link request")

    async def _work_queue(self) -> None:
        while True:
            sender_id, url, event = await self.queue.get()
            try:
                await self._record_and_deliver(sender_id, url)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Unhandled recording request failure")
                try:
                    await self.client.send_message(sender_id, "❌ रिकॉर्डिंग में त्रुटि आ गई। सर्वर लॉग में विवरण देखें।")
                except Exception:
                    pass
            finally:
                self.queue.task_done()

    async def _record_and_deliver(self, sender_id: int, url: str) -> None:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", url.rsplit("/", 1)[-1])[:24] or "youtube"
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
        await self.client.send_message(sender_id, "🔴 रिकॉर्डिंग शुरू हो रही है। स्ट्रीम समाप्त होने तक यह प्रक्रिया चल सकती है।")
        result = await self.recorder.record_stream(info, live_from_start=True)
        if result.status.value != "completed" or not result.output_path or not Path(result.output_path).is_file():
            reason = result.error or result.status.value
            await self.client.send_message(sender_id, f"❌ रिकॉर्डिंग पूरी नहीं हो सकी। कारण: {reason}")
            return

        output = Path(result.output_path)
        max_gb = self.splitting_config.premium_size_gb if self.uploader.is_premium else self.splitting_config.default_size_gb
        files = [str(output)]
        if output.stat().st_size > max_gb * 1024 * 1024 * 1024:
            splitter = FileSplitter(output_dir=str(output.parent))
            split_result = await splitter.split_file(str(output), max_gb, output_prefix=f"{output.stem}_part")
            if not split_result.success or not split_result.output_files:
                await self.client.send_message(sender_id, "❌ वीडियो बड़ी है और उसे Telegram की सीमा के अनुसार बाँटा नहीं जा सका। रिकॉर्डिंग सर्वर पर सुरक्षित रखी गई है।")
                return
            files = split_result.output_files

        await self.client.send_message(sender_id, f"📤 रिकॉर्डिंग पूरी हुई ({len(files)} फ़ाइल)। अब इसी चैट में भेज रहा हूँ…")
        total = len(files)
        for index, file_path in enumerate(files, start=1):
            caption = (
                f"🎬 YouTube Live recording\n"
                f"🔗 {url}\n"
                f"📦 Part {index}/{total}" if total > 1 else f"🎬 YouTube Live recording\n🔗 {url}"
            )
            upload = await self.uploader.upload_file(file_path, caption, target_channel_id=sender_id)
            if not upload.success:
                await self.client.send_message(
                    sender_id,
                    f"⚠️ फ़ाइल {index}/{total} भेजने में विफल रही: {upload.error or 'अज्ञात त्रुटि'}\n"
                    f"फ़ाइल सर्वर पर रखी गई है: {Path(file_path).name}"
                )
                return
        await self.client.send_message(sender_id, "✅ रिकॉर्डिंग की सभी फ़ाइलें भेज दी गई हैं।")
