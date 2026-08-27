import unittest

from carmaker_recorder.rsds_protocol import get_payload_size, header_to_words


class ProtocolTests(unittest.TestCase):
    def test_camera_header(self):
        raw = b"*CameraRSI 0 rgb 1.25 2x2 12".ljust(64, b"\x00")
        msg_type, parts = header_to_words(raw)
        self.assertEqual(msg_type, "CameraRSI")
        self.assertEqual(get_payload_size(msg_type, parts), (False, 12))

if __name__ == "__main__":
    unittest.main()
