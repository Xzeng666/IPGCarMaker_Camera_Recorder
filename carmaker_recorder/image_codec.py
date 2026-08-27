from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np


def choose_export_format(configured: str, fmt: str, payload_len: int, w: int, h: int) -> str:
    source_fmt = (fmt or "").lower()
    if configured.lower() != "auto":
        return configured.lower()

    if source_fmt in ("rgb", "bgr") and payload_len == w * h * 3:
        return "ppm"
    if source_fmt in ("g8", "gray", "grey") and payload_len == w * h:
        return "g8"
    if source_fmt == "g16" and payload_len == w * h * 2:
        return "g16"
    return "raw"


def build_image_header(export_fmt: str, w: int, h: int) -> Tuple[str, bytes]:
    export_fmt = export_fmt.lower()
    if export_fmt == "ppm":
        return "ppm", f"P6\n{w} {h}\n255\n".encode("ascii")
    if export_fmt == "g8":
        return "pgm", f"P5\n{w} {h}\n255\n".encode("ascii")
    if export_fmt == "g16":
        return "pgm", f"P5\n{w} {h}\n65535\n".encode("ascii")
    if export_fmt == "jpg":
        return "jpg", b""
    return "raw", b""


def prepare_export_payload(payload: bytes, source_fmt: str, export_fmt: str, w: int, h: int) -> bytes | None:
    """Return bytes conforming to the target raw image format.

    PPM P6 requires RGB channel order. PGM16 requires big-endian samples by the
    Netpbm specification. RAW remains byte-for-byte unchanged.
    """
    src = (source_fmt or "").lower()
    target = export_fmt.lower()
    if target == "raw":
        return payload
    if target == "ppm":
        arr = np.frombuffer(payload, dtype=np.uint8)
        if arr.size != w * h * 3 or src not in {"rgb", "bgr"}:
            return None
        frame = arr.reshape((h, w, 3))
        if src == "bgr":
            frame = frame[:, :, ::-1]
        return np.ascontiguousarray(frame).tobytes()
    if target == "g8":
        if src not in {"g8", "gray", "grey"} or len(payload) != w * h:
            return None
        return payload
    if target == "g16":
        if src != "g16" or len(payload) != w * h * 2:
            return None
        native = np.frombuffer(payload, dtype=np.uint16).reshape((h, w))
        return native.astype(">u2", copy=False).tobytes()
    return None


def decode_payload_to_bgr(payload: bytes, fmt: str, w: int, h: int) -> Optional[np.ndarray]:
    fmt = (fmt or "").lower()

    if fmt in ("rgb", "bgr"):
        arr = np.frombuffer(payload, dtype=np.uint8)
        if arr.size != w * h * 3:
            return None
        frame = arr.reshape((h, w, 3))
        if fmt == "rgb":
            return frame[:, :, ::-1].copy()
        return frame.copy()

    if fmt in ("gray", "grey", "g8"):
        arr = np.frombuffer(payload, dtype=np.uint8)
        if arr.size != w * h:
            return None
        return cv2.cvtColor(arr.reshape((h, w)), cv2.COLOR_GRAY2BGR)

    if fmt == "g16":
        arr = np.frombuffer(payload, dtype=np.uint16)
        if arr.size != w * h:
            return None
        g8 = (arr.reshape((h, w)) >> 8).astype(np.uint8)
        return cv2.cvtColor(g8, cv2.COLOR_GRAY2BGR)

    return None
