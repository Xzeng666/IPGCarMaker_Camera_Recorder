from __future__ import annotations

import logging
import socket
import threading
import time

from .config import AppConfig
from .models import Message
from .ring_buffer import RingBuffer
from .rsds_protocol import get_payload_size, header_to_words, read_header_resync, recv_exact

LOG = logging.getLogger(__name__)


class NetworkReceiver(threading.Thread):
    """Independent reconnecting RSDS receiver for one TCP port."""

    def __init__(
        self,
        host: str,
        port: int,
        msg_ring: RingBuffer[Message],
        global_exit_evt: threading.Event,
        config: AppConfig,
        monitor=None,
    ):
        super().__init__(daemon=True, name=f"RSDS-{host}-{port}")
        self.host = host
        self.port = int(port)
        self.msg_ring = msg_ring
        self.global_exit_evt = global_exit_evt
        self.config = config
        self.monitor = monitor
        self._sock: socket.socket | None = None
        self._sock_lock = threading.Lock()
        self.timeout_count = 0
        self.reconnect_count = 0
        self.messages_received = 0

    def _set_sock(self, sock: socket.socket | None) -> None:
        with self._sock_lock:
            self._sock = sock

    def _close_sock(self) -> None:
        with self._sock_lock:
            sock = self._sock
            self._sock = None
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def request_stop(self) -> None:
        self._close_sock()

    def _wait_retry(self) -> bool:
        self.reconnect_count += 1
        if self.monitor is not None:
            self.monitor.set_connection(self.port, "RETRYING")
        return self.global_exit_evt.wait(self.config.network.reconnect_delay_sec)

    def run(self) -> None:
        net = self.config.network
        try:
            while not self.global_exit_evt.is_set():
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    sock.settimeout(net.connect_timeout_sec)
                    self._set_sock(sock)
                    if self.monitor is not None:
                        self.monitor.set_connection(self.port, "CONNECTING")
                    sock.connect((self.host, self.port))
                    sock.settimeout(net.socket_timeout_sec)
                    self.timeout_count = 0
                    if self.monitor is not None:
                        self.monitor.set_connection(self.port, "CONNECTED")
                    LOG.info("[%s:%s] RSDS connected", self.host, self.port)

                    while not self.global_exit_evt.is_set():
                        try:
                            header = read_header_resync(sock, net.header_size)
                        except socket.timeout as exc:
                            self.timeout_count += 1
                            LOG.warning(
                                "[%s:%s] RSDS timeout (%s/%s)",
                                self.host, self.port, self.timeout_count, net.max_timeouts_before_reconnect,
                            )
                            if self.timeout_count >= net.max_timeouts_before_reconnect:
                                raise ConnectionError("consecutive RSDS timeouts exceeded limit") from exc
                            continue
                        if header is None:
                            raise ConnectionError("remote closed")
                        msg_type, parts = header_to_words(header)
                        if not msg_type:
                            continue
                        is_err, payload_size = get_payload_size(msg_type, parts)
                        if is_err:
                            LOG.warning("[%s:%s] invalid RSDS header: %r", self.host, self.port, header)
                            continue
                        if payload_size < 0 or payload_size > net.max_payload_bytes:
                            message = (
                                f"RSDS payload size {payload_size} exceeds configured safety limit "
                                f"{net.max_payload_bytes} bytes on port {self.port}"
                            )
                            if self.monitor is not None:
                                self.monitor.add_error(f"network:{self.port}", message, fatal=True)
                            self.global_exit_evt.set()
                            raise ConnectionError(message)
                        try:
                            data = recv_exact(sock, payload_size) if payload_size > 0 else None
                        except socket.timeout as exc:
                            self.timeout_count += 1
                            if self.timeout_count >= net.max_timeouts_before_reconnect:
                                raise ConnectionError("payload timeout limit exceeded") from exc
                            continue
                        if payload_size > 0 and data is None:
                            raise ConnectionError("remote closed during payload")

                        self.timeout_count = 0
                        self.messages_received += 1
                        overwritten = self.msg_ring.push_overwrite(
                            Message(
                                header=header, data=data, domain=self.host, port=self.port, received_epoch=time.time()
                            )
                        )
                        if overwritten and self.monitor is not None:
                            self.monitor.mark_network_drop(self.port)
                            self.monitor.set_message_buffer_stats(self.msg_ring.stats())
                            drops = self.msg_ring.stats().dropped
                            if drops == 1 or drops % 100 == 0:
                                LOG.warning("Message buffer overwrite detected: dropped=%s", drops)
                except (OSError, ConnectionError, TimeoutError, socket.timeout) as exc:
                    if not self.global_exit_evt.is_set():
                        LOG.info("[%s:%s] RSDS disconnected: %s", self.host, self.port, exc)
                finally:
                    self._close_sock()
                    if self.monitor is not None and not self.global_exit_evt.is_set():
                        self.monitor.set_connection(self.port, "DISCONNECTED")

                if self.global_exit_evt.is_set() or self._wait_retry():
                    break
        finally:
            self._close_sock()
            if self.monitor is not None:
                self.monitor.set_connection(self.port, "DISCONNECTED")
