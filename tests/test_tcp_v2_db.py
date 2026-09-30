"""Offline tests for safe handling of database API failures."""

from io import BytesIO
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from tcp_v2_config import Settings
from tcp_v2_db import DatabaseApiClient, DatabaseApiError


class DatabaseApiClientTests(unittest.TestCase):
    @patch("tcp_v2_db.urlopen")
    def test_html_error_response_is_not_passed_to_ui(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = HTTPError(
            "http://example.test/parts", 502, "Bad Gateway", {},
            BytesIO(b"<!doctype html><html><body>proxy error</body></html>"),
        )
        client = DatabaseApiClient(Settings())

        with self.assertRaises(DatabaseApiError) as caught:
            client.list_parts()

        self.assertIn("HTTP 502", str(caught.exception))
        self.assertIn("non-JSON error response", str(caught.exception))
        self.assertNotIn("<html", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
