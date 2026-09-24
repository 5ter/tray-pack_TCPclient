"""Compatibility client for the existing tray-packing database HTTP API."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tcp_v2_config import Settings


class DatabaseApiError(RuntimeError):
    """The existing database server did not complete an expected request."""


class DatabaseApiClient:
    """Call the unchanged `/get-project-data` and `/update-box-id` endpoints."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.db_base_url.rstrip("/")
        self._timeout = settings.db_timeout_seconds

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            try:
                details = json.loads(body)
                message = details.get("error") or details.get("message") or body
            except json.JSONDecodeError:
                message = body or error.reason
            raise DatabaseApiError(f"{path} returned HTTP {error.code}: {message}") from error
        except URLError as error:
            raise DatabaseApiError(f"Cannot reach database API at {self._base_url}: {error.reason}") from error

        try:
            result = json.loads(body)
        except json.JSONDecodeError as error:
            raise DatabaseApiError(f"{path} returned invalid JSON") from error
        if not isinstance(result, dict):
            raise DatabaseApiError(f"{path} returned JSON that is not an object")
        return result

    def get_project_data(self, spec: str) -> dict[str, Any]:
        return self._post("/get-project-data", {"spec": spec})

    def update_box_id(self, spec: str, new_box_id: str) -> dict[str, Any]:
        return self._post("/update-box-id", {"spec": spec, "newBoxId": new_box_id})
