"""Strongly owned, observable helpers for short-lived background work.

Long-running workers should keep an explicit owner reference and lifecycle.
This registry is for auxiliary tasks that intentionally outlive one request.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Coroutine
import logging
from typing import Any, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


class SupervisedTaskRegistry:
    """Own short background tasks until completion and consume their results."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._started = 0
        self._succeeded = 0
        self._failed = 0
        self._cancelled = 0
        self._closing = False

    def create_task(
        self,
        coroutine: Coroutine[Any, Any, T],
        *,
        name: str,
    ) -> asyncio.Task[T]:
        task_name = str(name or "background-task")[:120]
        if self._closing:
            coroutine.close()
            raise RuntimeError("background task registry is shutting down")
        try:
            task = asyncio.create_task(coroutine, name=task_name)
        except BaseException:
            coroutine.close()
            raise

        self._started += 1
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def begin_shutdown(self) -> None:
        """Reject new auxiliary work while producers are being stopped."""

        self._closing = True

    def start(self) -> None:
        """Open an empty registry for one application lifespan."""

        if self._tasks:
            raise RuntimeError("cannot start a background registry with live tasks")
        self._closing = False

    async def shutdown(
        self,
        *,
        timeout: float | None = 10.0,
    ) -> dict[str, Any]:
        """Cancel and drain all owned tasks before process dependencies close."""

        self.begin_shutdown()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()

        if tasks:
            _done, pending = await asyncio.wait(tasks, timeout=timeout)
            await asyncio.sleep(0)
            if pending:
                logger.error(
                    "Background task shutdown timed out pendingCount=%d",
                    len(pending),
                )
        return self.snapshot()

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            self._cancelled += 1
            return

        try:
            exception = task.exception()
        except asyncio.CancelledError:
            self._cancelled += 1
            return

        if exception is None:
            self._succeeded += 1
            return

        self._failed += 1
        logger.error(
            "Background task failed taskName=%s errorType=%s",
            task.get_name(),
            type(exception).__name__,
        )

    def snapshot(self) -> dict[str, Any]:
        running_by_name = Counter(task.get_name() for task in self._tasks)
        return {
            "running": len(self._tasks),
            "started": self._started,
            "succeeded": self._succeeded,
            "failed": self._failed,
            "cancelled": self._cancelled,
            "closing": self._closing,
            "runningByName": dict(sorted(running_by_name.items())),
        }


background_task_registry = SupervisedTaskRegistry()


def spawn_background_task(
    coroutine: Coroutine[Any, Any, T],
    *,
    name: str,
) -> asyncio.Task[T]:
    """Start one supervised short task using the process-wide registry."""

    return background_task_registry.create_task(coroutine, name=name)


def get_background_task_stats() -> dict[str, Any]:
    """Return a JSON-serializable snapshot for diagnostics and metrics."""

    return background_task_registry.snapshot()


def begin_background_task_shutdown() -> None:
    """Close the process-wide registry to new work."""

    background_task_registry.begin_shutdown()


def start_background_task_runtime() -> None:
    """Open the process-wide registry during application startup."""

    background_task_registry.start()


async def shutdown_background_tasks(
    *,
    timeout: float | None = 10.0,
) -> dict[str, Any]:
    """Cancel and drain all process-wide auxiliary tasks."""

    return await background_task_registry.shutdown(timeout=timeout)
