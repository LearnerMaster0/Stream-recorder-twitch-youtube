import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from streamrecorder.recorder import RecordingResult, RecordingStatus, StreamRecorder
from streamrecorder.stream_monitor import StreamInfo


class RecorderCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_youtube_live_from_start_uses_configured_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "recordings"
            temp_dir = Path(tmpdir) / "temp"
            recorder = StreamRecorder(
                output_dir=str(output_dir),
                temp_dir=str(temp_dir),
                format_spec="bestvideo*+bestaudio/best",
                live_from_start=True,
                move_atom_to_front=False,
            )
            stream_info = StreamInfo(
                channel="testchannel",
                title="Test live",
                category="Education",
                stream_url="https://www.youtube.com/watch?v=abcdefghijk",
                is_live=True,
            )
            now = datetime.now()
            recorder.recover_interrupted_recording = AsyncMock(
                return_value=RecordingResult(
                    channel=stream_info.channel,
                    stream_info=stream_info,
                    output_path="",
                    status=RecordingStatus.FAILED,
                    duration_seconds=0,
                    file_size_bytes=0,
                    started_at=now,
                    ended_at=now,
                    error="test recovery stub",
                )
            )
            process = SimpleNamespace(
                returncode=0,
                stdout=SimpleNamespace(readline=AsyncMock(return_value=b"")),
                wait=AsyncMock(),
            )

            with patch(
                "streamrecorder.recorder.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=process),
            ) as create_process:
                await recorder.record_stream(stream_info)

            command = create_process.await_args.args
            format_index = command.index("--format")
            self.assertEqual(command[format_index + 1], "bestvideo*+bestaudio/best")
            self.assertIn("--live-from-start", command)
            self.assertEqual(command[command.index("--retries") + 1], "10")
            self.assertEqual(command[command.index("--fragment-retries") + 1], "10")
            self.assertEqual(command[command.index("--socket-timeout") + 1], "120")
            self.assertEqual(command[-1], stream_info.stream_url)

    async def test_youtube_403_does_not_fall_back_to_live_edge(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = StreamRecorder(
                output_dir=str(Path(tmpdir) / "recordings"),
                temp_dir=str(Path(tmpdir) / "temp"),
                format_spec="bv*+ba/b",
                live_from_start=True,
                move_atom_to_front=False,
            )
            stream_info = StreamInfo(
                channel="testchannel",
                title="Test live",
                category="Education",
                stream_url="https://www.youtube.com/watch?v=abcdefghijk",
                is_live=True,
            )
            now = datetime.now()
            recorder.recover_interrupted_recording = AsyncMock(
                return_value=RecordingResult(
                    channel=stream_info.channel,
                    stream_info=stream_info,
                    output_path="",
                    status=RecordingStatus.FAILED,
                    duration_seconds=0,
                    file_size_bytes=0,
                    started_at=now,
                    ended_at=now,
                    error="test recovery stub",
                )
            )
            first_process = SimpleNamespace(
                returncode=1,
                stdout=SimpleNamespace(
                    readline=AsyncMock(side_effect=[b"HTTP Error 403: Forbidden\\n", b""])
                ),
                wait=AsyncMock(),
            )

            with patch(
                "streamrecorder.recorder.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=first_process),
            ) as create_process:
                result = await recorder.record_stream(stream_info)

            self.assertEqual(create_process.await_count, 1)
            command = create_process.await_args.args
            self.assertIn("--live-from-start", command)
            self.assertEqual(result.status, RecordingStatus.FAILED)
            self.assertIn("Refusing to retry from the current live edge", result.error)



if __name__ == "__main__":
    unittest.main()
