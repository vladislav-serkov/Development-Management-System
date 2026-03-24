from typing import Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DependencyEntry(Base):
    __tablename__ = "dependency_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    registry_type: Mapped[str] = mapped_column(String(20))  # "db", "external_api", "cache"
    name: Mapped[str] = mapped_column(String(255))
    data_json: Mapped[str] = mapped_column(Text)  # Full registry JSON blob

    __table_args__ = (UniqueConstraint("document_id", "registry_type", "name"),)

    def __repr__(self) -> str:
        return f"<DependencyEntry id={self.id} registry_type={self.registry_type} name={self.name}>"


class GapEntry(Base):
    __tablename__ = "gap_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(20))  # "DB", "API", "Cache"
    name: Mapped[str] = mapped_column(String(255))
    affected_features: Mapped[str] = mapped_column(Text)  # JSON list of feature names
    what_missing: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20))  # "critical", "medium", "low"
    suggestion_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<GapEntry id={self.id} category={self.category} name={self.name}>"
