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

    def test_missing_file_is_reported_and_does_not_shift_album_message_mapping(self):
        messages = [types.SimpleNamespace(id=101), types.SimpleNamespace(id=103)]

        results = _album_upload_results(
            ["part1.mp4", "missing.mp4", "part3.mp4"],
            messages,
            valid_indices=[0, 2],
        )

        self.assertEqual(len(results), 3)
        self.assertEqual([result.message_id for result in results], [101, None, 103])
        self.assertTrue(results[0].success)
        self.assertFalse(results[1].success)
        self.assertIn("missing", results[1].error.lower())
        self.assertTrue(results[2].success)


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

    async def test_album_with_all_missing_files_returns_explicit_failures(self):
        uploader = TelegramUploader(1, "hash", -1001)
        uploader._client = object()

        results = await uploader._upload_album(
            stream_info=StreamInfo(channel="channel", title="title", category="cat"),
            file_paths=["missing-part1.mp4", "missing-part2.mp4"],
            start_part_num=1,
            total_parts=2,
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(not item.success for item in results))
        self.assertTrue(all("missing" in item.error.lower() for item in results))

    async def test_album_exception_returns_failed_result_for_every_file(self):
        uploader = TelegramUploader(1, "hash", -1001)
        uploader._client = object()

        async def fail_album(**kwargs):
            raise RuntimeError("simulated Telegram album failure")

        uploader._upload_album = fail_album
        result = await uploader.upload_stream_parts(
            stream_info=StreamInfo(channel="channel", title="title", category="cat"),
            file_paths=[f"part{i}.mp4" for i in range(1, 4)],
            total_parts_override=3,
        )

        self.assertEqual(result.total_parts, 3)
        self.assertEqual(result.failed_uploads, 3)
        self.assertEqual(len(result.results), 3)
        self.assertTrue(all(not item.success for item in result.results))
        self.assertTrue(all("simulated Telegram album failure" in item.error for item in result.results))

    async def test_partial_resume_preserves_original_part_numbers_and_album_groups(self):
        uploader = TelegramUploader(1, "hash", -1001)
        calls = []

        async def fake_upload_album(**kwargs):
            calls.append(kwargs)
            return [
                UploadResult(path, part_number + 100, True)
                for path, part_number in zip(
                    kwargs["file_paths"],
                    kwargs["part_numbers_override"],
                )
            ]

        uploader._client = object()
        uploader._upload_album = fake_upload_album

        result = await uploader.upload_stream_parts(
            stream_info=StreamInfo(channel="channel", title="title", category="cat"),
            file_paths=["part003.mp4", "part007.mp4", "part011.mp4"],
            start_part_num=3,
            total_parts_override=12,
            album_index_offset=0,
            album_total_override=2,
            part_numbers_override=[3, 7, 11],
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["file_paths"], ["part003.mp4", "part007.mp4"])
        self.assertEqual(calls[0]["part_numbers_override"], [3, 7])
        self.assertEqual(calls[0]["album_index"], 1)
        self.assertEqual(calls[1]["file_paths"], ["part011.mp4"])
        self.assertEqual(calls[1]["part_numbers_override"], [11])
        self.assertEqual(calls[1]["album_index"], 2)
        self.assertEqual([item.message_id for item in result.results], [103, 107, 111])

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
