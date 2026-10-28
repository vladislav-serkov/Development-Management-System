"""Single-origin production entrypoint: the API under ``/api`` + the built SPA.

Mirrors what the Vite dev proxy and the nginx config do (``/api/*`` → API with
the prefix stripped), so the frontend code is identical in dev and prod and the
session cookie is same-origin. Run with ``uvicorn app.serve:app``.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.main import app as api_app

ROOT = Path(__file__).resolve().parent.parent


class SPAStaticFiles(StaticFiles):
    """Unknown paths fall back to index.html so client-side routes survive a reload."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Mounted sub-apps don't get lifespan events — run the API's (migrations, engine) here
    async with api_app.router.lifespan_context(api_app):
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", api_app)

dist = Path(settings.frontend_dist)
if not dist.is_absolute():
    dist = ROOT / dist
app.mount("/", SPAStaticFiles(directory=dist, html=True, check_dir=False), name="spa")
