import unittest

from carmaker_recorder.config import SCHEMA_VERSION, config_from_dict
from tests.helpers import latest_config_dict


class ConfigSafetyTests(unittest.TestCase):
    def test_legacy_schema_is_rejected(self):
        raw = latest_config_dict()
        raw["schema_version"] = 2
        with self.assertRaises(ValueError):
            config_from_dict(raw)

    def test_invalid_camera_filename_is_rejected(self):
        raw = latest_config_dict(output={"camera_names": {"0": "FRONT/LEFT"}})
        with self.assertRaises(ValueError):
            config_from_dict(raw)

    def test_duplicate_camera_output_names_are_rejected(self):
        raw = latest_config_dict(output={"camera_names": {"0": "FRONT", "1": "front"}})
        with self.assertRaises(ValueError):
            config_from_dict(raw)

    def test_empty_video_extension_is_rejected(self):
        raw = latest_config_dict(video={"extension": ""})
        with self.assertRaises(ValueError):
            config_from_dict(raw)

    def test_video_acceleration_settings_are_validated(self):
        for field, value in (
            ("backend", "cuda"),
            ("codec", "vp9"),
            ("bitrate_mbps", 0),
            ("ffmpeg_path", ""),
        ):
            with self.subTest(field=field):
                raw = latest_config_dict(video={field: value})
                with self.assertRaises(ValueError):
                    config_from_dict(raw)

    def test_preview_hz_is_preserved(self):
        cfg = config_from_dict(latest_config_dict(gui={"live_preview": True, "preview_hz": 3.5}))
        self.assertEqual(cfg.schema_version, SCHEMA_VERSION)
        self.assertEqual(cfg.gui.preview_hz, 3.5)

    def test_current_schema_missing_field_is_rejected(self):
        raw = latest_config_dict()
        del raw["network"]["header_size"]
        with self.assertRaises(ValueError):
            config_from_dict(raw)

    def test_unknown_root_or_section_field_is_rejected(self):
        raw = latest_config_dict()
        raw["compatibility"] = {}
        with self.assertRaises(ValueError):
            config_from_dict(raw)

        raw = latest_config_dict()
        raw["images"]["hz"] = 10.0
        with self.assertRaises(ValueError):
            config_from_dict(raw)

    def test_camera_ids_are_strict_and_payload_limit_is_validated(self):
        raw = latest_config_dict(output={"camera_names": {"0": "A", "00": "B"}})
        with self.assertRaises(ValueError):
            config_from_dict(raw)
        raw = latest_config_dict(output={"camera_names": {"-1": "A"}})
        with self.assertRaises(ValueError):
            config_from_dict(raw)
        raw = latest_config_dict(network={"max_payload_bytes": 1024})
        with self.assertRaises(ValueError):
            config_from_dict(raw)


if __name__ == "__main__":
    unittest.main()
