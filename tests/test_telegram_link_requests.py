import unittest

from streamrecorder.telegram_link_requests import YOUTUBE_URL_RE


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

    def test_ignores_non_youtube_links(self):
        self.assertIsNone(YOUTUBE_URL_RE.search("https://twitch.tv/example"))
        self.assertIsNone(YOUTUBE_URL_RE.search("just a message"))

    def test_extracts_link_from_surrounding_text(self):
        text = "Please record this: https://youtu.be/abc123 thanks!"
        self.assertEqual(YOUTUBE_URL_RE.search(text).group(0), "https://youtu.be/abc123")


if __name__ == "__main__":
    unittest.main()
