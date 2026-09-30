"""Compatibility client for the existing tray-packing database HTTP API."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from tcp_v2_config import Settings


class DatabaseApiError(RuntimeError):
    """The existing database server did not complete an expected request."""


class DatabaseApiClient:
    """Call the part-number and inspection-result HTTP API."""

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

    def _get(self, path: str) -> Any:
        request = Request(f"{self._base_url}{path}", method="GET")
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
            return json.loads(body)
        except json.JSONDecodeError as error:
            raise DatabaseApiError(f"{path} returned invalid JSON") from error

    def list_parts(self) -> list[dict[str, str]]:
        response = self._get("/parts")
        if not isinstance(response, list):
            raise DatabaseApiError("/parts returned JSON that is not a list")
        parts: list[dict[str, str]] = []
        for part in response:
            if not isinstance(part, dict) or not isinstance(part.get("partNumber"), str):
                raise DatabaseApiError("/parts returned an invalid part-number entry")
            parts.append({"partNumber": part["partNumber"]})
        return parts

    def record_inspection(self, payload: dict[str, str]) -> dict[str, Any]:
        return self._post("/inspection-results", payload)

    def record_inspection_batch(self, events: list[dict[str, str]]) -> list[str]:
        response = self._post("/inspection-results/batch", {"events": events})
        accepted_ids = response.get("acceptedEventIds")
        if not isinstance(accepted_ids, list) or any(not isinstance(event_id, str) for event_id in accepted_ids):
            raise DatabaseApiError("/inspection-results/batch returned an invalid acceptedEventIds list")
        return accepted_ids

    def get_run_summary(self, run_id: str, part_number: str) -> dict[str, Any]:
        query = urlencode({"runId": run_id, "partNumber": part_number})
        response = self._get(f"/run-summary?{query}")
        if not isinstance(response, dict):
            raise DatabaseApiError("/run-summary returned JSON that is not an object")
        return response
