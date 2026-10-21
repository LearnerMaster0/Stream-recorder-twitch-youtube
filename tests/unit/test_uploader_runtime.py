import asyncio
import sys
import types
import unittest

from streamrecorder.stream_monitor import StreamInfo


telethon = types.ModuleType("telethon")
telethon.TelegramClient = object
tl = types.ModuleType("telethon.tl")
tl_types = types.ModuleType("telethon.tl.types")
tl_types.User = object
tl_types.DocumentAttributeVideo = object
tl_types.DocumentAttributeFilename = object
tl_types.InputMediaUploadedDocument = object
sys.modules.setdefault("telethon", telethon)
sys.modules.setdefault("telethon.tl", tl)
sys.modules.setdefault("telethon.tl.types", tl_types)

from streamrecorder.uploader import BatchUploadResult, TelegramUploader, UploadResult, _album_upload_results


class AlbumResponseMappingTests(unittest.TestCase):
    def test_missing_telegram_album_messages_are_reported_as_failed_files(self):
        messages = [types.SimpleNamespace(id=101), types.SimpleNamespace(id=102)]

        results = _album_upload_results(
            ["part1.mp4", "part2.mp4", "part3.mp4"],
            messages,
        )

        self.assertEqual(len(results), 3)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].message_id, 101)
        self.assertTrue(results[1].success)
        self.assertEqual(results[1].message_id, 102)
        self.assertFalse(results[2].success)
        self.assertIsNone(results[2].message_id)
        self.assertIn("fewer album messages", results[2].error)

    def test_message_without_id_is_not_reported_as_success(self):
        results = _album_upload_results(
            ["part1.mp4"],
            [types.SimpleNamespace(id=None)],
        )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIsNotNone(results[0].error)


class UploaderRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_runtime_serializes_and_restores_settings(self):
        uploader = TelegramUploader(1, "hash", -1001, upload_parallelism=1, upload_speed_limit_mbps=0)
        events = []

        async def run_with_runtime(name, parallelism, speed):
            async with uploader.upload_runtime(parallelism, speed):
                events.append((name, uploader.upload_parallelism, uploader.upload_speed_limit_mbps))
                await asyncio.sleep(0.01)

        await asyncio.gather(
            run_with_runtime("first", 2, 5),
            run_with_runtime("second", 4, 9),
        )

        self.assertEqual(events, [("first", 2, 5.0), ("second", 4, 9.0)])
        self.assertEqual(uploader.upload_parallelism, 1)
        self.assertEqual(uploader.upload_speed_limit_mbps, 0.0)

    async def test_upload_stream_parts_resume_numbering_for_albums(self):
        uploader = TelegramUploader(1, "hash", -1001)
        calls = []

        async def fake_upload_album(**kwargs):
            calls.append(kwargs)
            return [UploadResult(path, idx + 1, True) for idx, path in enumerate(kwargs["file_paths"])]

        uploader._client = object()
        uploader._upload_album = fake_upload_album

        result = await uploader.upload_stream_parts(
            stream_info=StreamInfo(channel="channel", title="title", category="cat"),
            file_paths=["part011.mp4", "part012.mp4"],
            duration_str="",
            start_part_num=11,
            total_parts_override=12,
            album_index_offset=1,
            album_total_override=2,
        )

        self.assertIsInstance(result, BatchUploadResult)
        self.assertEqual(result.total_parts, 12)
        self.assertEqual(calls[0]["start_part_num"], 11)
        self.assertEqual(calls[0]["total_parts"], 12)
        self.assertEqual(calls[0]["album_index"], 2)
        self.assertEqual(calls[0]["album_total"], 2)


if __name__ == "__main__":
    unittest.main()
