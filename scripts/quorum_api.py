"""A tiny HTTP client for the Quorum API, standard library only.

The operator scripts beside this one run on a bare `python3` — no virtual
environment, no `requests` — so the plumbing they share (a cookie jar, JSON
encoding, the backend's `Origin` check on mutations, and its `{"detail": ...}`
errors) lives here rather than being written twice.
"""

import json
import os
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_WEB_ORIGIN = "http://localhost:3000"


def default_base_url() -> str:
    return os.environ.get("QUORUM_BASE_URL", DEFAULT_BASE_URL)


def default_web_origin() -> str:
    return os.environ.get("QUORUM_WEB_ORIGIN", DEFAULT_WEB_ORIGIN)


class ApiError(Exception):
    """A non-2xx answer, carrying the backend's status and its `detail`."""

    def __init__(self, status: int, detail: str, method: str, path: str):
        super().__init__(f"{method} {path} -> {status}: {detail}")
        self.status = status
        self.detail = detail


class Client:
    """One session against one backend, holding whatever cookies it is given.

    The backend refuses a mutation whose `Origin` it does not allow, so every
    request carries the web origin the browser would have sent. `base_url` is
    the backend itself: these scripts talk to it directly rather than through
    the Next.js rewrite, which is why the two are separate settings.
    """

    def __init__(self, base_url: str, web_origin: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.web_origin = web_origin.rstrip("/")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def request(self, method: str, path: str, body: dict | None = None):
        data = None
        headers = {"Accept": "application/json", "Origin": self.web_origin}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            raise ApiError(error.code, _detail(error.read()), method, path) from error
        except urllib.error.URLError as error:
            raise ApiError(0, f"could not reach {self.base_url}: {error.reason}", method, path) from error
        return json.loads(payload) if payload else None

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body: dict | None = None):
        return self.request("POST", path, body)

    def put(self, path: str, body: dict):
        return self.request("PUT", path, body)


def _detail(payload: bytes) -> str:
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return payload.decode("utf-8", "replace").strip() or "no detail"
    detail = parsed.get("detail") if isinstance(parsed, dict) else None
    return detail if isinstance(detail, str) else json.dumps(parsed)
