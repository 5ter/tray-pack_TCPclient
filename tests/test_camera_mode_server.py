"""Loopback tests for the camera-mode TCP protocol."""

import socket
import unittest

from tcp_v2_camera_server import CameraModeTcpServer


class CameraModeTcpServerTests(unittest.TestCase):
    def test_two_camera_clients_receive_updates_and_can_query_mode(self) -> None:
        server = CameraModeTcpServer("127.0.0.1", 0)
        clients: list[socket.socket] = []
        streams = []
        try:
            server.start()
            assert server._server is not None
            address = server._server.server_address
            for _ in range(2):
                client = socket.create_connection(address, timeout=2)
                client.settimeout(2)
                clients.append(client)
                streams.append(client.makefile("rb"))
                self.assertEqual(streams[-1].readline(), b"MODE=UNKNOWN\r\n")

            server.update_mode(1)
            for stream in streams:
                self.assertEqual(stream.readline(), b"MODE=1\r\n")

            clients[0].sendall(b"GET_MODE\r\n")
            self.assertEqual(streams[0].readline(), b"MODE=1\r\n")
        finally:
            for stream in streams:
                stream.close()
            for client in clients:
                client.close()
            server.stop()


if __name__ == "__main__":
    unittest.main()
