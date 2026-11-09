"""A scripted HTTP stub on 127.0.0.1 for the loopback tests of the live path's mechanics (1.7.0).

OFFLINE: the stub listens on the loopback interface only, and the request worker it talks to refuses every
other target while live mode is disabled. The test process itself never connects (tests/conftest.py still
refuses it): only the isolated worker, a child process, does.
"""

from __future__ import annotations

import gzip
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

Behaviour = Callable[["Connection"], None]


@dataclass
class Connection:
    sock: socket.socket
    head: bytes = b""
    body: bytes = b""
    opened_at: float = 0.0
    closed_at: float | None = None
    stop: threading.Event = field(default_factory=threading.Event)

    def send(self, data: bytes) -> bool:
        try:
            self.sock.sendall(data)
            return True
        except OSError:
            self.closed_at = self.closed_at or time.monotonic()
            return False

    def wait_closed(self, limit_s: float = 60.0) -> None:
        """Hold the connection open until the client closes it (or the stub stops)."""
        self.sock.settimeout(0.05)
        end = time.monotonic() + limit_s
        while time.monotonic() < end and not self.stop.is_set():
            try:
                if self.sock.recv(4096) == b"":
                    break
            except TimeoutError:
                continue
            except OSError:
                break
        self.closed_at = self.closed_at or time.monotonic()


def _read_request(sock: socket.socket) -> tuple[bytes, bytes]:
    sock.settimeout(10.0)
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 1_000_000:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value.strip())
    while len(rest) < length:
        chunk = sock.recv(65536)
        if not chunk:
            break
        rest += chunk
    return head, rest


class Stub:
    """Answers each connection with the next behaviour (the last one repeats)."""

    def __init__(self, *behaviours: Behaviour) -> None:
        assert behaviours
        self.behaviours = list(behaviours)
        self.connections: list[Connection] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self._sock.settimeout(0.05)
        self.port = int(self._sock.getsockname()[1])
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._accept = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> Stub:
        self._accept.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        for c in self.connections:
            c.stop.set()
        self._accept.join(5)
        for t in self._threads:
            t.join(5)
        self._sock.close()

    def _serve(self) -> None:
        n = 0
        while not self._stop.is_set():
            try:
                sock, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            behaviour = self.behaviours[min(n, len(self.behaviours) - 1)]
            n += 1
            conn = Connection(sock, opened_at=time.monotonic())
            self.connections.append(conn)
            t = threading.Thread(target=self._handle, args=(conn, behaviour), daemon=True)
            self._threads.append(t)
            t.start()

    def _handle(self, conn: Connection, behaviour: Behaviour) -> None:
        try:
            conn.head, conn.body = _read_request(conn.sock)
            behaviour(conn)
        except OSError:
            pass
        finally:
            conn.closed_at = conn.closed_at or time.monotonic()
            try:
                conn.sock.close()
            except OSError:
                pass

    def authorizations(self) -> list[str]:
        """How many times the Authorization header arrived (its value is never shown)."""
        out = []
        for c in self.connections:
            for line in c.head.split(b"\r\n")[1:]:
                if line.lower().startswith(b"authorization:"):
                    out.append("present")
        return out


def respond(status: int, body: bytes = b"{}", headers: dict[str, str] | None = None) -> Behaviour:
    def run(conn: Connection) -> None:
        lines = [f"HTTP/1.1 {status} Stub", f"Content-Length: {len(body)}", "Connection: close"]
        lines += [f"{k}: {v}" for k, v in (headers or {}).items()]
        conn.send(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)

    return run


def redirect(status: int, location: str) -> Behaviour:
    return respond(status, b"", {"Location": location})


def hang(conn: Connection) -> None:
    """Read the request and never answer."""
    conn.wait_closed()


def drip(total: int, every_s: float) -> Behaviour:
    """A body announced whole and sent one byte at a time."""

    def run(conn: Connection) -> None:
        if not conn.send(f"HTTP/1.1 200 OK\r\nContent-Length: {total}\r\nConnection: close\r\n\r\n".encode()):
            return
        for _ in range(total):
            if conn.stop.is_set() or not conn.send(b"{"):
                return
            time.sleep(every_s)

    return run


def endless(status: int = 200) -> Behaviour:
    """A body without a length that never ends (until the client goes away)."""

    def run(conn: Connection) -> None:
        if not conn.send(f"HTTP/1.1 {status} Stub\r\nConnection: close\r\n\r\n".encode()):
            return
        block = b"x" * 65536
        while not conn.stop.is_set() and conn.send(block):
            pass

    return run


def gzip_bomb(decoded_bytes: int) -> Behaviour:
    data = gzip.compress(b"\0" * decoded_bytes, compresslevel=9)
    return respond(200, data, {"Content-Encoding": "gzip", "Content-Type": "application/json"})


def short(status: int, declared: int, body: bytes) -> Behaviour:
    """A body announced at ``declared`` bytes, of which ``body`` is sent before the connection is closed (the
    client's review of 1.7.1, finding C4: Content-Length 100, the two bytes ``{}``, then a close)."""

    def run(conn: Connection) -> None:
        head = f"HTTP/1.1 {status} Stub\r\nContent-Length: {declared}\r\nConnection: close\r\n\r\n"
        conn.send(head.encode("latin-1") + body)

    return run


def chunked_short(status: int, chunk_size: int, body: bytes) -> Behaviour:
    """A chunked body whose first chunk announces ``chunk_size`` bytes, of which ``body`` is sent before the
    connection is closed."""

    def run(conn: Connection) -> None:
        head = f"HTTP/1.1 {status} Stub\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        conn.send(head.encode("latin-1") + f"{chunk_size:x}\r\n".encode("ascii") + body)

    return run


def no_body(status: int) -> Behaviour:
    """A status that has no body by definition (204, 304), sent without a Content-Length."""

    def run(conn: Connection) -> None:
        conn.send(f"HTTP/1.1 {status} Stub\r\nConnection: close\r\n\r\n".encode("latin-1"))

    return run
