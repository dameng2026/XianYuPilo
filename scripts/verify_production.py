#!/usr/bin/env python3
"""Secret-file-aware, cross-platform production deployment verifier.

Secret contents are read only into this process and the short-lived Docker
Compose child environment. They are never placed in command arguments or
printed, and the resulting containers receive only /run/secrets file paths.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator, Sequence
from urllib import parse, request

if __package__:
    from . import production_preflight
else:  # pragma: no cover - direct deployment entry point
    import production_preflight


MAX_READINESS_BODY_BYTES = 64 * 1024
ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE_FILE = ROOT / "docker-compose.yml"
COMPOSE_PROJECT_NAME = "xianyu-assistant"
UNSAFE_AMBIENT_COMPOSE_FIELDS = (
    "COMPOSE_FILE",
    "COMPOSE_PROJECT_NAME",
    "COMPOSE_PROFILES",
    "COMPOSE_ENV_FILES",
    "COMPOSE_PATH_SEPARATOR",
    "COMPOSE_DISABLE_ENV_FILE",
)


def compose_argv(
    env_file: Path,
    *arguments: str,
    compose_files: Sequence[Path] = (),
) -> list[str]:
    argv = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "--project-name",
        COMPOSE_PROJECT_NAME,
    ]
    for compose_file in compose_files:
        argv.extend(("--file", str(compose_file)))
    argv.extend(arguments)
    return argv


def compose_environment(
    values: dict[str, str],
    base_environment: dict[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(os.environ if base_environment is None else base_environment)
    for field_name in UNSAFE_AMBIENT_COMPOSE_FIELDS:
        environment.pop(field_name, None)
    for field_name in production_preflight.FILE_SECRET_FIELDS:
        environment[field_name] = values.get(field_name, "")
    environment.setdefault("COMPOSE_ANSI", "never")
    return environment


def run_compose(
    env_file: Path,
    values: dict[str, str],
    *arguments: str,
    check: bool = True,
    compose_files: Sequence[Path] = (),
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        compose_argv(env_file, *arguments, compose_files=compose_files),
        check=check,
        shell=False,
        cwd=ROOT,
        env=compose_environment(values),
    )


def deployment_up_arguments(*, no_build: bool, wait_timeout: int) -> tuple[str, ...]:
    build_policy = "--no-build" if no_build else "--build"
    return (
        "up",
        "-d",
        build_policy,
        "--wait",
        "--wait-timeout",
        str(wait_timeout),
    )


def probe_readiness(url: str, *, timeout: int, require_hsts: bool) -> None:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("Readiness URL must use HTTP or HTTPS.")
    probe = request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "xianyu-release-verifier/1"},
        method="GET",
    )
    with request.urlopen(probe, timeout=timeout) as response:  # nosec B310 - scheme checked
        if getattr(response, "status", None) != 200:
            raise RuntimeError("Readiness endpoint did not return HTTP 200.")
        body = response.read(MAX_READINESS_BODY_BYTES + 1)
        if len(body) > MAX_READINESS_BODY_BYTES:
            raise RuntimeError("Readiness response exceeded the safe size limit.")
        if require_hsts:
            hsts = str(response.headers.get("Strict-Transport-Security", ""))
            if "max-age=" not in hsts.lower():
                raise RuntimeError("Public TLS readiness response did not include HSTS.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Readiness endpoint did not return valid JSON.") from exc
    if payload != {"status": "ready"}:
        raise RuntimeError("Readiness endpoint did not return the coarse ready payload.")


def _print_report(report: production_preflight.ValidationReport) -> None:
    for error in report.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for warning in report.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def _verify_deployment(
    env_path: Path,
    values: dict[str, str],
    *,
    no_build: bool,
    wait_timeout: int,
    compose_files: Sequence[Path],
) -> int:
    try:
        run_compose(env_path, values, "version", compose_files=compose_files)
        # Quiet is mandatory: a resolved Compose document must never be emitted.
        run_compose(
            env_path,
            values,
            "config",
            "--quiet",
            compose_files=compose_files,
        )
        up_arguments = deployment_up_arguments(
            no_build=no_build,
            wait_timeout=wait_timeout,
        )
        run_compose(
            env_path,
            values,
            *up_arguments,
            compose_files=compose_files,
        )
    except FileNotFoundError:
        print("ERROR: Docker Engine and Compose v2 are required.", file=sys.stderr)
        return 127
    except subprocess.CalledProcessError:
        try:
            run_compose(
                env_path,
                values,
                "ps",
                check=False,
                compose_files=compose_files,
            )
        except OSError:
            pass
        print("ERROR: Production container validation or startup failed.", file=sys.stderr)
        return 1

    web_port = values.get("WEB_PORT", "8080").strip() or "8080"
    public_base_url = values.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    try:
        probe_readiness(
            f"http://127.0.0.1:{web_port}/readyz",
            timeout=10,
            require_hsts=False,
        )
        probe_readiness(
            f"{public_base_url}/readyz",
            timeout=15,
            require_hsts=True,
        )
    except Exception:
        print("ERROR: Local or public TLS readiness verification failed.", file=sys.stderr)
        return 1

    try:
        run_compose(env_path, values, "ps", compose_files=compose_files)
    except (OSError, subprocess.CalledProcessError):
        print("ERROR: Could not read final Compose service state.", file=sys.stderr)
        return 1
    print("Production readiness passed locally and through the configured TLS origin.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate, start, and verify the production stack without exposing secrets"
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=300)
    args = parser.parse_args(argv)
    if not 30 <= args.wait_timeout <= 1800:
        print("ERROR: WAIT_TIMEOUT must be between 30 and 1800 seconds.", file=sys.stderr)
        return 64

    env_path = Path(args.env_file).resolve()
    parse_report = production_preflight.ValidationReport()
    values = production_preflight.load_env(
        env_path,
        parse_report,
        require_secret_files=True,
    )
    report = production_preflight.validate(values, env_path)
    report.errors[:0] = parse_report.errors
    report.warnings[:0] = parse_report.warnings
    if report.errors:
        _print_report(report)
        print(
            f"Production preflight failed with {len(report.errors)} error(s).",
            file=sys.stderr,
        )
        return 2
    _print_report(report)

    return _verify_deployment(
        env_path,
        values,
        no_build=args.no_build,
        wait_timeout=args.wait_timeout,
        compose_files=(BASE_COMPOSE_FILE,),
    )


if __name__ == "__main__":
    raise SystemExit(main())
