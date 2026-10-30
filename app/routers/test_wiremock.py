from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import wiremock

router = APIRouter(prefix="/test-wiremock", tags=["test-wiremock"])


class UploadMockRequest(BaseModel):
    mock_config: str = Field(..., min_length=1, max_length=100_000)


@router.get("/status")
async def test_wiremock_status():
    url = wiremock.mappings_url()
    return {"configured": url is not None, "target_url": url}


@router.post("/upload")
async def upload_mock(body: UploadMockRequest):
    if not wiremock.mappings_url():
        raise HTTPException(status_code=503, detail="WireMock не настроен — задайте TEST_WIREMOCK_URL в .env")
    try:
        mapping = wiremock.prepare_mapping(body.mock_config)
    except wiremock.InvalidMappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return await wiremock.upload_mapping(mapping)
    except wiremock.WireMockError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
