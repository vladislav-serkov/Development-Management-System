from pydantic import BaseModel


class ExportRequest(BaseModel):
    target_path: str | None = None  # Absolute path to target microservice root (optional)
    feature_name: str | None = None  # If None, export all features in document


class ExportResponse(BaseModel):
    exported_features: list[str]
    target_path: str
    files_written: list[str]
