from __future__ import annotations

import unittest

import numpy as np

from carmaker_recorder.image_codec import (
    build_image_header,
    choose_export_format,
    decode_payload_to_bgr,
    prepare_export_payload,
)


class ImageCodecMatrixTests(unittest.TestCase):
    def test_auto_format_matrix_and_headers(self):
        self.assertEqual(choose_export_format("auto", "rgb", 6, 2, 1), "ppm")
        self.assertEqual(choose_export_format("auto", "bgr", 6, 2, 1), "ppm")
        self.assertEqual(choose_export_format("auto", "g8", 2, 2, 1), "g8")
        self.assertEqual(choose_export_format("auto", "g16", 4, 2, 1), "g16")
        self.assertEqual(choose_export_format("auto", "unknown", 3, 1, 1), "raw")
        self.assertEqual(build_image_header("ppm", 2, 1), ("ppm", b"P6\n2 1\n255\n"))
        self.assertEqual(build_image_header("g8", 2, 1)[0], "pgm")
        self.assertEqual(build_image_header("g16", 2, 1)[0], "pgm")
        self.assertEqual(build_image_header("jpg", 2, 1), ("jpg", b""))
        self.assertEqual(build_image_header("raw", 2, 1), ("raw", b""))

    def test_decode_rgb_bgr_gray_and_g16(self):
        rgb = bytes([255, 0, 0])
        bgr = decode_payload_to_bgr(rgb, "rgb", 1, 1)
        self.assertEqual(bgr[0, 0].tolist(), [0, 0, 255])

        source_bgr = bytes([1, 2, 3])
        bgr2 = decode_payload_to_bgr(source_bgr, "bgr", 1, 1)
        self.assertEqual(bgr2[0, 0].tolist(), [1, 2, 3])

        gray = decode_payload_to_bgr(bytes([77]), "g8", 1, 1)
        self.assertEqual(gray[0, 0].tolist(), [77, 77, 77])

        native = np.array([0xAB00], dtype=np.uint16).tobytes()
        g16 = decode_payload_to_bgr(native, "g16", 1, 1)
        self.assertEqual(g16[0, 0].tolist(), [0xAB, 0xAB, 0xAB])

    def test_invalid_payloads_are_rejected(self):
        self.assertIsNone(decode_payload_to_bgr(b"\x00", "rgb", 1, 1))
        self.assertIsNone(decode_payload_to_bgr(b"\x00", "unsupported", 1, 1))
        self.assertIsNone(prepare_export_payload(b"\x00", "g8", "ppm", 1, 1))
        self.assertIsNone(prepare_export_payload(b"\x00", "g16", "g16", 1, 1))
        self.assertEqual(prepare_export_payload(b"abc", "whatever", "raw", 1, 1), b"abc")
        self.assertEqual(prepare_export_payload(b"\x05", "gray", "g8", 1, 1), b"\x05")


if __name__ == "__main__":
    unittest.main()
