from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from carmaker_recorder.config import VideoConfig
from carmaker_recorder.video_encoder import create_video_encoder


class VideoEncoderSelectionTests(unittest.TestCase):
    @patch("carmaker_recorder.video_encoder.OpenCvVideoEncoder")
    @patch(
        "carmaker_recorder.video_encoder.available_hardware_backend", return_value=None
    )
    def test_auto_mode_falls_back_to_opencv(self, _available, opencv):
        instance = Mock(backend_name="opencv:FFMPEG:XVID")
        opencv.return_value = instance
        encoder, reason = create_video_encoder(
            Path("capture.avi"),
            VideoConfig(),
            640,
            480,
        )
        self.assertIs(encoder, instance)
        self.assertIn("unavailable", reason)

    @patch(
        "carmaker_recorder.video_encoder.available_hardware_backend", return_value=None
    )
    def test_required_hardware_backend_fails_closed(self, _available):
        config = VideoConfig(backend="nvenc", allow_cpu_fallback=False)
        with self.assertRaises(RuntimeError):
            create_video_encoder(Path("capture.avi"), config, 640, 480)

    @patch("carmaker_recorder.video_encoder.FfmpegHardwareEncoder")
    @patch(
        "carmaker_recorder.video_encoder.available_hardware_backend",
        return_value=("ffmpeg", "nvenc", "h264_nvenc"),
    )
    def test_available_hardware_backend_is_selected(self, _available, ffmpeg_encoder):
        instance = Mock(backend_name="ffmpeg:h264_nvenc")
        ffmpeg_encoder.return_value = instance
        encoder, reason = create_video_encoder(
            Path("capture.avi"),
            VideoConfig(backend="nvenc"),
            640,
            480,
        )
        self.assertIs(encoder, instance)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
