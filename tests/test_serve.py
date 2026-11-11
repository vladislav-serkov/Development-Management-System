"""Production static serving: SPA fallback, page revalidation, missing build files."""

import httpx
import pytest
from fastapi import FastAPI

from app.serve import SPAStaticFiles


@pytest.fixture
async def site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<script type="module" src="/assets/index-NEW.js"></script>')
    (tmp_path / "assets" / "index-NEW.js").write_text("console.log('new build')")
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=tmp_path, html=True), name="spa")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://site") as client:
        yield client


@pytest.mark.parametrize("url", ["/", "/index.html", "/projects/p/features/pay-later.payment.queue/tests"])
async def test_the_page_is_revalidated_on_every_load(site, url):
    r = await site.get(url)
    assert r.status_code == 200
    assert "index-NEW.js" in r.text
    assert r.headers["cache-control"] == "no-cache"


async def test_a_file_of_a_replaced_build_is_not_answered_with_the_page(site):
    r = await site.get("/assets/index-OLD.js")
    assert r.status_code == 404
    assert "index-NEW.js" not in r.text


async def test_build_files_are_served_as_they_are(site):
    r = await site.get("/assets/index-NEW.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert "cache-control" not in r.headers
