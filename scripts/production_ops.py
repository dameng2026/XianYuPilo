#!/usr/bin/env python3
"""Secret-file-aware operational access to the production Compose stack.

This entry point deliberately exposes only a small, fixed command surface. It
loads protected secret files into a short-lived Docker Compose child process,
never into command arguments or the persistent parent environment.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import BinaryIO, TextIO

if __package__:
    from . import production_preflight, verify_production
else:  # pragma: no cover - direct production entry point
    import production_preflight
    import verify_production


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = (ROOT / "docker-compose.yml",)
ALLOWED_SERVICES = ("mysql", "redis", "migrate", "api", "worker", "crawler", "web")
DEFAULT_LOG_TAIL = 200
MAX_LOG_TAIL = 10_000


class UsageError(Exception):
    """Raised for a rejected command line without echoing untrusted input."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise UsageError


def _log_tail(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("invalid log tail") from exc
    if not 1 <= parsed <= MAX_LOG_TAIL:
        raise argparse.ArgumentTypeError("invalid log tail")
    return parsed


def _parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(
        description="Inspect or stop the production stack without exposing secret-file contents."
    )
    parser.add_argument("--env-file", default=".env")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show all Compose service states.")
    commands.add_parser(
        "stop",
        help="Stop and remove stack containers and networks while preserving named volumes.",
    )
    logs = commands.add_parser("logs", help="Read redacted Compose service logs.")
    logs.add_argument("--follow", action="store_true")
    logs.add_argument("--tail", type=_log_tail, default=DEFAULT_LOG_TAIL)
    logs.add_argument("services", nargs="*", choices=ALLOWED_SERVICES)
    return parser


def _load_secret_values(env_path: Path) -> tuple[dict[str, str], list[str]]:
    report = production_preflight.ValidationReport()
    values = production_preflight.load_env(
        env_path,
        report,
        require_secret_files=True,
    )
    return values, report.errors


def _secret_bytes(values: dict[str, str]) -> tuple[bytes, ...]:
    return tuple(
        sorted(
        {
            value.encode("utf-8")
            for field_name in production_preflight.FILE_SECRET_FIELDS
            if (value := values.get(field_name, ""))
        },
        key=len,
        reverse=True,
        )
    )


def _redact_with(data: bytes, secrets: tuple[bytes, ...]) -> bytes:
    redacted = data
    for secret in secrets:
        redacted = redacted.replace(secret, b"[REDACTED]")
    return redacted


def _redact(data: bytes, values: dict[str, str]) -> bytes:
    return _redact_with(data, _secret_bytes(values))


class StreamingSecretRedactor:
    """Redact exact secrets while retaining enough bytes for split matches."""

    def __init__(self, values: dict[str, str]):
        self._secrets = _secret_bytes(values)
        self._pending = b""
        self._longest = max((len(secret) for secret in self._secrets), default=0)

    def feed(self, chunk: bytes) -> bytes:
        self._pending += chunk
        if not self._secrets:
            output, self._pending = self._pending, b""
            return output
        cut = max(0, len(self._pending) - self._longest + 1)
        while cut:
            adjusted = cut
            for secret in self._secrets:
                search_from = max(0, cut - len(secret) + 1)
                match = self._pending.find(secret, search_from)
                while 0 <= match < cut:
                    if match + len(secret) > cut:
                        adjusted = min(adjusted, match)
                        break
                    match = self._pending.find(secret, match + 1)
            if adjusted == cut:
                break
            cut = adjusted
        output = _redact_with(self._pending[:cut], self._secrets)
        self._pending = self._pending[cut:]
        return output

    def finish(self) -> bytes:
        output = _redact_with(self._pending, self._secrets)
        self._pending = b""
        return output


def _write_bytes(stream: TextIO, data: bytes) -> None:
    binary_stream: BinaryIO | None = getattr(stream, "buffer", None)
    if binary_stream is not None:
        binary_stream.write(data)
        binary_stream.flush()
    else:  # pragma: no cover - primarily for embedded/text-only consoles
        stream.write(data.decode("utf-8", errors="replace"))
        stream.flush()


def _run_captured(
    env_path: Path,
    values: dict[str, str],
    arguments: tuple[str, ...],
) -> int:
    completed = subprocess.run(
        verify_production.compose_argv(
            env_path,
            *arguments,
            compose_files=COMPOSE_FILES,
        ),
        check=False,
        shell=False,
        cwd=ROOT,
        env=verify_production.compose_environment(values),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _write_bytes(sys.stdout, _redact(completed.stdout, values))
    _write_bytes(sys.stderr, _redact(completed.stderr, values))
    return completed.returncode


def _run_streaming(
    env_path: Path,
    values: dict[str, str],
    arguments: tuple[str, ...],
) -> int:
    process = subprocess.Popen(  # noqa: S603 - fixed executable and allowlisted arguments
        verify_production.compose_argv(
            env_path,
            *arguments,
            compose_files=COMPOSE_FILES,
        ),
        shell=False,
        cwd=ROOT,
        env=verify_production.compose_environment(values),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if process.stdout is None:  # pragma: no cover - guarded by stdout=PIPE
        raise RuntimeError("Compose log stream was unavailable.")
    redactor = StreamingSecretRedactor(values)
    try:
        while chunk := process.stdout.read(8192):
            _write_bytes(sys.stdout, redactor.feed(chunk))
        _write_bytes(sys.stdout, redactor.finish())
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        return 130


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except UsageError:
        print("ERROR: Invalid operation arguments; use --help for the fixed command surface.", file=sys.stderr)
        return 64

    env_path = Path(args.env_file).resolve()
    values, errors = _load_secret_values(env_path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("ERROR: Protected production secret files could not be loaded.", file=sys.stderr)
        return 2

    try:
        if args.command == "status":
            return _run_captured(env_path, values, ("ps", "--all"))
        if args.command == "stop":
            return _run_captured(env_path, values, ("down",))
        if args.command == "logs":
            compose_arguments: tuple[str, ...] = (
                "logs",
                "--no-color",
                "--tail",
                str(args.tail),
            )
            if args.follow:
                compose_arguments += ("--follow",)
            compose_arguments += tuple(args.services)
            if args.follow:
                return _run_streaming(env_path, values, compose_arguments)
            return _run_captured(env_path, values, compose_arguments)
    except FileNotFoundError:
        print("ERROR: Docker Engine and Compose v2 are required.", file=sys.stderr)
        return 127
    except OSError:
        print("ERROR: The production operation could not be executed.", file=sys.stderr)
        return 1
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
