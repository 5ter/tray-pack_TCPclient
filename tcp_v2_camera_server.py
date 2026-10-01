"""TCP service that publishes the cached PLC camera-mode register to cameras."""

from __future__ import annotations

import logging
import queue
import socket
import socketserver
from threading import Lock, Thread


_STOP = object()


class _CameraRequestHandler(socketserver.BaseRequestHandler):
    """Send the current mode on connect and answer optional GET_MODE requests."""

    def setup(self) -> None:
        self.request.settimeout(0.5)
        self.server.register_client(self.request)
        logging.info("Camera TCP client connected from %s", self.client_address[0])

    def handle(self) -> None:
        buffer = bytearray()
        while True:
            try:
                chunk = self.request.recv(256)
            except socket.timeout:
                continue
            except OSError:
                return
            if not chunk:
                return

            buffer.extend(chunk)
            if len(buffer) > 256 and b"\n" not in buffer:
                logging.warning("Camera TCP request exceeded 256 bytes; dropping connection")
                return

            while b"\n" in buffer:
                line, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)
                command = line.rstrip(b"\r").decode("ascii", errors="replace").strip().upper()
                if command == "GET_MODE":
                    self.server.send_current_mode(self.request)
                elif command:
                    logging.debug("Ignoring camera TCP command %r from %s", command, self.client_address[0])

    def finish(self) -> None:
        self.server.unregister_client(self.request)
        logging.info("Camera TCP client disconnected from %s", self.client_address[0])


class _ThreadedCameraServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], owner: "CameraModeTcpServer") -> None:
        self.owner = owner
        self._clients: dict[socket.socket, Lock] = {}
        self._clients_lock = Lock()
        super().__init__(address, _CameraRequestHandler)

    @staticmethod
    def _payload(mode: int | None) -> bytes:
        value = "UNKNOWN" if mode is None else str(mode)
        return f"MODE={value}\r\n".encode("ascii")

    def register_client(self, client: socket.socket) -> None:
        with self._clients_lock:
            self._clients[client] = Lock()
        self.send_current_mode(client)

    def unregister_client(self, client: socket.socket) -> None:
        with self._clients_lock:
            self._clients.pop(client, None)

    def send_current_mode(self, client: socket.socket) -> None:
        with self._clients_lock:
            send_lock = self._clients.get(client)
        if send_lock is None:
            return
        with send_lock:
            try:
                client.sendall(self._payload(self.owner.current_mode()))
            except OSError:
                self.unregister_client(client)

    def broadcast_mode(self) -> None:
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            self.send_current_mode(client)


class CameraModeTcpServer:
    """Serve cached D1 values without adding network I/O to PLC polling."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._mode: int | None = None
        self._mode_lock = Lock()
        self._publish_queue: queue.Queue[object] = queue.Queue()
        self._server: _ThreadedCameraServer | None = None
        self._server_thread: Thread | None = None
        self._publisher_thread: Thread | None = None

    def current_mode(self) -> int | None:
        with self._mode_lock:
            return self._mode

    def update_mode(self, mode: int | None) -> None:
        """Cache a new D1 value and queue a push to connected cameras if changed."""
        if mode is not None and not 0 <= mode <= 65_535:
            raise ValueError("Camera mode must be a 16-bit unsigned value or None")
        with self._mode_lock:
            if self._mode == mode:
                return
            self._mode = mode
        logging.info("PLC camera mode is now %s", "UNKNOWN" if mode is None else mode)
        self._publish_queue.put(mode)

    def _publish_loop(self) -> None:
        while True:
            mode = self._publish_queue.get()
            if mode is _STOP:
                return
            server = self._server
            if server is not None:
                server.broadcast_mode()

    def start(self) -> None:
        if self._server_thread is not None:
            return
        server = _ThreadedCameraServer((self._host, self._port), self)
        self._server = server
        self._publisher_thread = Thread(target=self._publish_loop, name="camera-mode-publisher", daemon=True)
        self._server_thread = Thread(target=server.serve_forever, name="camera-mode-tcp", daemon=True)
        self._publisher_thread.start()
        self._server_thread.start()
        bound_host, bound_port = server.server_address[:2]
        logging.info("Camera mode TCP server listening at %s:%s", bound_host, bound_port)

    def stop(self) -> None:
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self._server = None
        self._publish_queue.put(_STOP)
        if self._server_thread is not None:
            self._server_thread.join(timeout=3)
        if self._publisher_thread is not None:
            self._publisher_thread.join(timeout=3)
        self._server_thread = None
        self._publisher_thread = None
