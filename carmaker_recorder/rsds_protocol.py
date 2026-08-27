from __future__ import annotations

import socket
from typing import Optional, Tuple


def recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = bytearray(n)
    mv = memoryview(buf)
    got = 0
    while got < n:
        try:
            read = sock.recv_into(mv[got:], n - got)
        except socket.timeout:
            raise
        except OSError:
            return None
        if read == 0:
            return None
        got += read
    return bytes(buf)


def read_header_resync(sock: socket.socket, header_size: int) -> Optional[bytes]:
    hdr = recv_exact(sock, header_size)
    if hdr is None:
        return None

    while True:
        if len(hdr) == header_size and hdr[0] == ord("*") and ord("A") <= hdr[1] <= ord("Z"):
            return hdr

        idx = hdr.find(b"*", 1)
        if idx < 0:
            hdr = recv_exact(sock, header_size)
            if hdr is None:
                return None
            continue

        remain = hdr[idx:]
        extra = recv_exact(sock, header_size - len(remain))
        if extra is None:
            return None
        hdr = remain + extra


def header_to_words(header: bytes) -> Tuple[str, list[str]]:
    text = header.decode("ascii", errors="ignore").strip("\x00 ").strip()
    if not text:
        return "", []
    parts = text.split()
    msg_type = parts[0]
    if msg_type.startswith("*"):
        msg_type = msg_type[1:]
    return msg_type, parts


def get_payload_size(msg_type: str, parts: list[str]) -> Tuple[bool, int]:
    try:
        if msg_type == "CameraRSI":
            return False, int(parts[5])
        if msg_type == "CameraRSIEmbeddedData":
            return False, int(parts[3])
        if msg_type in ("RadarRSI", "LidarRSI", "USonicRSI"):
            return False, int(parts[2])
        if msg_type in ("IPGMovie", "MovieNX"):
            return False, 0
    except (IndexError, TypeError, ValueError):
        return True, 0
    return True, 0
