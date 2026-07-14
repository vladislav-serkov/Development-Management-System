"""Centralized background task manager.

Tracks all asyncio background tasks and logs their outcome. Replaces
per-router fire-and-forget patterns with a single registry.
"""

import asyncio
import logging
from typing import Awaitable

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def launch(self, key: str, coro: Awaitable) -> bool:
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
                logger.error("Task failed: %s — %s", key, t.exception())

        task.add_done_callback(_on_done)
        logger.info("Task launched: %s", key)
        return True

    def is_running(self, key: str) -> bool:
        """Check if a task is currently running."""
        task = self._tasks.get(key)
        return task is not None and not task.done()


# Singleton instance — import and use across routers
task_manager = TaskManager()
