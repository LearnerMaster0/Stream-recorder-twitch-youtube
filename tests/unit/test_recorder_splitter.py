import tempfile
import unittest
from pathlib import Path

from streamrecorder.recorder import StreamRecorder
from streamrecorder.splitter import FileSplitter


class RecorderConfigTests(unittest.TestCase):
    def test_retry_values_use_configured_counts(self):
        recorder = StreamRecorder(retries=7, fragment_retries=8)

        self.assertEqual(recorder._retry_value(recorder.retries), "7")
        self.assertEqual(recorder._retry_value(recorder.fragment_retries), "8")


class SplitterValidationTests(unittest.TestCase):
    def test_rejects_non_positive_size(self):
        splitter = FileSplitter()

        with self.assertRaisesRegex(ValueError, "max_size_gb"):
            splitter.needs_splitting("missing.mp4", 0)

    def test_accepts_numeric_string_size(self):
        splitter = FileSplitter()

        self.assertFalse(splitter.needs_splitting("missing.mp4", "1.8"))


class SplitterSmallFileTests(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_small_recording_as_one_complete_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "recording.mp4"
            source.write_bytes(b"x" * 1024)

            result = await FileSplitter().split_file(str(source), max_size_gb=1.8)

            self.assertTrue(result.success)
            self.assertEqual(result.output_files, [str(source)])
            self.assertEqual(result.part_count, 1)


if __name__ == "__main__":
    unittest.main()
