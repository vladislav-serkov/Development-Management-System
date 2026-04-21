"""
Entry point for running the FastAPI backend as a Tauri sidecar.

Binds uvicorn on an OS-assigned port (port=0), then prints the actual
port to stdout in a parseable format so the parent Tauri process can
discover the backend URL.
"""
import asyncio
import os
import sys

# Restrict CORS to the Tauri webview in desktop mode. Must be set before
# app.main is imported — pydantic-settings reads env at import time.
os.environ.setdefault("CORS_ORIGINS", "tauri://localhost")

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402


PORT_SENTINEL = "EXTRACT_AGENT_PORT"

# Force line-buffered stdout so the port sentinel reaches the parent
# process immediately (PyInstaller bundles buffer by block otherwise).
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass


async def run() -> None:
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    serve_task = asyncio.create_task(server.serve())

    while not server.started:
        if serve_task.done():
            serve_task.result()
            return
        await asyncio.sleep(0.05)

    sockets = server.servers[0].sockets if server.servers else []
    if not sockets:
        raise RuntimeError("uvicorn bound no sockets — cannot determine port")
    port = sockets[0].getsockname()[1]
    print(f"{PORT_SENTINEL}={port}", flush=True)
    sys.stdout.flush()

    await serve_task


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
