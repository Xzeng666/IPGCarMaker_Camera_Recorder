from dataclasses import dataclass
from typing import Optional

ReadableBuffer = bytes | bytearray | memoryview


@dataclass(slots=True)
class Message:
    header: bytes | bytearray
    data: Optional[ReadableBuffer]
    domain: str
    port: int
    received_epoch: float


@dataclass(slots=True)
class CamFrame:
    cam_id: str
    fmt: str
    sim_time: float
    width: int
    height: int
    payload: ReadableBuffer
    received_epoch: float = 0.0
    source_port: int = 0


@dataclass(slots=True)
class ImageTask:
    cam_id: str
    fmt: str
    sim_time: float
    width: int
    height: int
    payload: ReadableBuffer
    domain: str
    port: int
