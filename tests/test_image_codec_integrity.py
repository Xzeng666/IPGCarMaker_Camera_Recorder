import unittest

from carmaker_recorder.image_codec import prepare_export_payload


class ImageCodecIntegrityTests(unittest.TestCase):
    def test_bgr_is_converted_to_rgb_for_ppm(self):
        payload = bytes([1, 2, 3])  # B,G,R
        self.assertEqual(prepare_export_payload(payload, "bgr", "ppm", 1, 1), bytes([3, 2, 1]))

    def test_g16_pgm_is_big_endian(self):
        payload = bytes([0x34, 0x12])  # native little-endian 0x1234 on target platforms
        self.assertEqual(prepare_export_payload(payload, "g16", "g16", 1, 1), bytes([0x12, 0x34]))


if __name__ == "__main__":
    unittest.main()
