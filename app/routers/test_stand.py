from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.services import http_runner
from app.storage import ProjectStore

store = ProjectStore()

router = APIRouter(
    prefix="/projects/{project_slug}/features/{feature_name}/test-stand",
    tags=["test-stand"],
)


class ExecuteHttpRequest(BaseModel):
    method: str = Field(..., min_length=1, max_length=10)
    path: str = Field(..., min_length=1, max_length=10_000)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(default=None, max_length=100_000)

    @field_validator("method")
    @classmethod
    def _known_method(cls, v: str) -> str:
        method = v.upper()
        if method not in http_runner.ALLOWED_METHODS:
            raise ValueError(f"Unsupported HTTP method: {v}")
        return method

    @field_validator("path")
    @classmethod
    def _path_only(cls, v: str) -> str:
        # The stand host is fixed by config — the artifact contributes only path+query
        if "://" in v.split("?", 1)[0] or v.startswith("//"):
            raise ValueError("path must be relative to the test stand, not an absolute URL")
        return v


async def _resolve_service(project_slug: str, feature_name: str) -> str | None:
    feature = await store.get_feature(project_slug, feature_name)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_name}' not found in project '{project_slug}'",
        )
    doc_slug = feature.get("source_document")
    if not doc_slug:
        return None
    doc = await store.get_document(project_slug, doc_slug)
    return (doc or {}).get("service_name")


@router.get("")
async def test_stand_status(project_slug: str, feature_name: str):
    """Whether a test stand is configured, and the target base for this feature."""
    if not http_runner.is_configured():
        return await http_runner.stand_info(None)
    service = await _resolve_service(project_slug, feature_name)
    return await http_runner.stand_info(service)


@router.post("/execute")
async def execute_http(project_slug: str, feature_name: str, body: ExecuteHttpRequest):
    """Run an HTTP request from a curl artifact against the test stand."""
    if not http_runner.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Тестовый стенд не настроен — задайте TEST_STAND_URL в .env",
        )
    service = await _resolve_service(project_slug, feature_name)
    prefix = await http_runner.resolve_route_prefix(service)
    url = http_runner.build_target_url(prefix, body.path)
    return await http_runner.execute_request(body.method, url, body.headers, body.body)
