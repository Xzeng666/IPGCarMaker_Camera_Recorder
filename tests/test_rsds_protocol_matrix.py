from __future__ import annotations

import socket
import unittest

from carmaker_recorder.rsds_protocol import (
    get_payload_size,
    header_to_words,
    read_header_resync,
    recv_exact,
)


class RsdsProtocolMatrixTests(unittest.TestCase):
    def test_payload_size_message_types_and_invalid_headers(self):
        self.assertEqual(get_payload_size("CameraRSIEmbeddedData", ["*CameraRSIEmbeddedData", "0", "x", "12"]), (False, 12))
        self.assertEqual(get_payload_size("RadarRSI", ["*RadarRSI", "0", "20"]), (False, 20))
        self.assertEqual(get_payload_size("LidarRSI", ["*LidarRSI", "0", "21"]), (False, 21))
        self.assertEqual(get_payload_size("USonicRSI", ["*USonicRSI", "0", "22"]), (False, 22))
        self.assertEqual(get_payload_size("MovieNX", ["*MovieNX"]), (False, 0))
        self.assertEqual(get_payload_size("Unknown", ["*Unknown"]), (True, 0))
        self.assertEqual(get_payload_size("CameraRSI", ["*CameraRSI"]), (True, 0))

    def test_recv_exact_and_header_resync(self):
        left, right = socket.socketpair()
        try:
            payload = b"abcdef"
            left.sendall(payload)
            received = recv_exact(right, len(payload))
            self.assertIsInstance(received, bytearray)
            self.assertEqual(received, payload)
        finally:
            left.close(); right.close()

        left, right = socket.socketpair()
        try:
            size = 32
            valid = b"*CameraRSI 0 rgb 0 1x1 3".ljust(size, b"\x00")
            # The first fixed block contains junk then the beginning of a valid header;
            # read_header_resync must preserve from '*' and fill the remainder.
            stream = b"XXXX" + valid
            left.sendall(stream)
            left.shutdown(socket.SHUT_WR)
            header = read_header_resync(right, size)
            self.assertIsNotNone(header)
            msg_type, parts = header_to_words(header)
            self.assertEqual(msg_type, "CameraRSI")
            self.assertEqual(parts[1], "0")
        finally:
            left.close(); right.close()

    def test_recv_exact_returns_none_on_closed_peer(self):
        left, right = socket.socketpair()
        left.close()
        try:
            self.assertIsNone(recv_exact(right, 4))
        finally:
            right.close()


if __name__ == "__main__":
    unittest.main()
