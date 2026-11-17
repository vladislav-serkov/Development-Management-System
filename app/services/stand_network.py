"""Telling "the platform cannot reach the stand" apart from errors of the stand itself.

A failed connection (DNS, refused, no route, connect timeout) is not something
a tester or the assistant can fix by changing a script or a request: the
platform host has lost its network path to the stand (usually the corporate
VPN). Results flag it as ``unreachable`` so the UI can point to the person who
looks after the platform instead of suggesting to fix the case.
"""
from __future__ import annotations

import socket

import httpx


def http_unreachable(exc: Exception) -> bool:
    """The request never reached the stand (no connection was made)."""
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))


def describe_http_error(exc: Exception, timeout: float) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return f"нет соединения со стендом за {timeout:g}с"
    if isinstance(exc, httpx.TimeoutException):
        return f"Таймаут запроса ({timeout:g}с)"
    return str(exc).strip() or exc.__class__.__name__


def describe_db_connect_error(exc: Exception, timeout: float) -> str:
    """Readable cause of a failed connect; asyncpg timeouts carry no message."""
    if isinstance(exc, TimeoutError):
        return f"нет ответа за {timeout:g}с"
    if isinstance(exc, socket.gaierror):
        return f"имя хоста не найдено ({exc})"
    return str(exc).strip() or exc.__class__.__name__
