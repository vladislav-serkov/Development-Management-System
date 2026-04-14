"""Centralized background task manager.

Tracks all asyncio background tasks, detects stuck states, logs errors.
Replaces per-router fire-and-forget patterns with a single registry.
"""

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def launch(
        self,
        key: str,
        coro: Awaitable,
        on_error: Callable[[str, BaseException], Awaitable[None]] | None = None,
    ) -> bool:
        """Launch a background task. Returns False if already running for this key."""
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            logger.info("Task already running: %s", key)
            return False

        task = asyncio.create_task(coro, name=key)
        self._tasks[key] = task

        def _on_done(t: asyncio.Task) -> None:
            self._tasks.pop(key, None)
            if t.cancelled():
                logger.warning("Task cancelled: %s", key)
            elif t.exception() is not None:
                exc = t.exception()
                logger.error("Task failed: %s — %s", key, exc)
                if on_error is not None:
                    asyncio.create_task(on_error(key, exc))

        task.add_done_callback(_on_done)
        logger.info("Task launched: %s", key)
        return True

    def is_running(self, key: str) -> bool:
        """Check if a task is currently running."""
        task = self._tasks.get(key)
        return task is not None and not task.done()

    def recover_stuck(self, key: str) -> bool:
        """Check if a key has no live task (stuck state). Returns True if stuck and cleaned up."""
        task = self._tasks.get(key)
        if task is not None and not task.done():
            return False  # task is alive, not stuck
        # No live task — clean up stale entry if present
        self._tasks.pop(key, None)
        return True

    @property
    def running_keys(self) -> list[str]:
        return [k for k, t in self._tasks.items() if not t.done()]


# Singleton instance — import and use across routers
task_manager = TaskManager()
