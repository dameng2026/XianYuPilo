"""Shared, secret-safe helpers for the repository's read-only smoke scripts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import requests


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def normalized_base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base URL must be an absolute HTTP(S) URL")
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if (
        parsed.scheme == "http"
        and parsed.hostname not in local_hosts
        and os.getenv("XYA_ALLOW_INSECURE_HTTP", "").lower() not in {"1", "true", "yes"}
    ):
        raise ValueError(
            "refusing to send credentials over remote HTTP; use HTTPS or explicitly set "
            "XYA_ALLOW_INSECURE_HTTP=1 in an isolated test environment"
        )
    return value


def create_authenticated_session(api_root: str, timeout: float) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    token = os.getenv("XYA_TEST_TOKEN", "").strip()
    verify_tls = os.getenv("XYA_INSECURE_TLS", "").lower() not in {"1", "true", "yes"}
    session.verify = verify_tls
    if not verify_tls:
        print("WARNING: TLS certificate verification is disabled for this smoke run.")

    if not token:
        password = os.getenv("XYA_TEST_PASSWORD", "")
        if not password:
            raise RuntimeError(
                "set XYA_TEST_TOKEN, or set XYA_TEST_PASSWORD for the dedicated smoke-test account"
            )
        username = os.getenv("XYA_TEST_USERNAME", "admin").strip() or "admin"
        response = session.post(
            f"{api_root}/auth/login",
            json={"username": username, "password": password},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = _json_object(response)
        token = str((payload.get("data") or {}).get("token") or "").strip()
        if not token:
            raise RuntimeError("login response did not contain an access token")

    # The token is intentionally never returned separately or printed.
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def check_json_get(
    session: requests.Session,
    api_root: str,
    endpoint: str,
    name: str,
    timeout: float,
) -> CheckResult:
    try:
        response = session.get(f"{api_root}{endpoint}", timeout=timeout, allow_redirects=False)
        payload = _json_object(response)
        envelope_code = payload.get("code")
        ok = response.status_code == 200 and envelope_code in {None, 0, 200}
        detail = f"HTTP {response.status_code}"
        if envelope_code is not None:
            detail += f", code={envelope_code}"
        return CheckResult(name, ok, detail)
    except requests.RequestException as exc:
        return CheckResult(name, False, f"request failed: {type(exc).__name__}")
    except ValueError:
        return CheckResult(name, False, "response was not a JSON object")


def _json_object(response: requests.Response) -> dict:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("response is not a JSON object")
    return payload
