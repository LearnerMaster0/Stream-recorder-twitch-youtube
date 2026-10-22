import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from streamrecorder.telegram_link_requests import TelegramLinkRequestHandler, YOUTUBE_URL_RE


class YouTubeLinkDetectionTests(unittest.TestCase):
    def test_accepts_common_youtube_live_links(self):
        urls = [
            "https://www.youtube.com/live/abc123",
            "https://youtube.com/watch?v=abc123",
            "https://youtu.be/abc123",
            "https://m.youtube.com/live/abc123",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(YOUTUBE_URL_RE.search(url).group(0), url)


    def test_queue_persists_requests_across_handler_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "requests.sqlite3")
            env = {"LINK_REQUESTS_DB": db_path, "TELEGRAM_ALLOWED_USER_IDS": "123"}
            with patch.dict(os.environ, env, clear=False):
                first = TelegramLinkRequestHandler(
                    client=None, recorder=None, uploader=None,
                    splitting_config=SimpleNamespace(default_size_gb=1.8, premium_size_gb=3.8),
                )
                with first._db() as db:
                    db.execute(
                        "INSERT INTO link_requests(sender_id,url,status,created_at,updated_at) "
                        "VALUES(123,'https://youtu.be/abc123','queued','now','now')"
                    )
                second = TelegramLinkRequestHandler(
                    client=None, recorder=None, uploader=None,
                    splitting_config=SimpleNamespace(default_size_gb=1.8, premium_size_gb=3.8),
                )
                with second._db() as db:
                    row = db.execute("SELECT sender_id,url,status FROM link_requests").fetchone()
                self.assertEqual((row["sender_id"], row["url"], row["status"]),
                                 (123, "https://youtu.be/abc123", "queued"))

    def test_ignores_non_youtube_links(self):
        self.assertIsNone(YOUTUBE_URL_RE.search("https://twitch.tv/example"))
        self.assertIsNone(YOUTUBE_URL_RE.search("just a message"))

    def test_extracts_link_from_surrounding_text(self):
        text = "Please record this: https://youtu.be/abc123 thanks!"
        self.assertEqual(YOUTUBE_URL_RE.search(text).group(0), "https://youtu.be/abc123")


if __name__ == "__main__":
    unittest.main()
