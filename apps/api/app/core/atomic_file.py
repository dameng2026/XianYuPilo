"""Small, synchronous primitives for publishing already-flushed files."""

from __future__ import annotations

import os
import time
from pathlib import Path


def atomic_replace_with_retry(
    source: Path,
    destination: Path,
    *,
    windows_retry_seconds: float = 0.25,
) -> None:
    """Atomically replace a file, tolerating brief Windows sharing locks.

    Readers and concurrent writers can briefly hold a destination without delete
    sharing on Windows. Retry only that narrow platform error for a bounded
    interval; permanent permission errors still fail.
    """

    source_path = Path(source)
    destination_path = Path(destination)
    deadline = time.monotonic() + max(float(windows_retry_seconds), 0.0)
    delay = 0.001
    while True:
        try:
            os.replace(source_path, destination_path)
            return
        except PermissionError:
            if os.name != "nt" or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.025)
