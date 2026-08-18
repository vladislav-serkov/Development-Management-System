"""SQLAlchemy models.

Moderate normalization: real tables + FKs for the entity graph, JSONB ``data``
columns for the (deeply nested, recursive) payloads so a row round-trips to the
exact dict shape the API served from the old file-based store.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Source .context/ directory this project was imported from (export-context target)
    context_dir: Mapped[str | None] = mapped_column(Text)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB)
    # Raw imported page (markdown + links + tables) — the extraction pipeline's input
    source: Mapped[dict | None] = mapped_column(JSONB)


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB)
    apply_preview: Mapped[dict | None] = mapped_column(JSONB)


class AnalysisItem(Base):
    """One gap / test case / bug. Lists are replaced wholesale by the API,
    so rows carry a position to preserve order; status/archived are promoted
    for filtering and counting."""

    __tablename__ = "analysis_items"
    __table_args__ = (
        UniqueConstraint("feature_id", "kind", "position"),
        Index("ix_analysis_items_feature_kind", "feature_id", "kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)  # gap | test_case | bug
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    data: Mapped[dict] = mapped_column(JSONB)


class Dependency(Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        # Case-insensitive uniqueness within a project + dep type
        Index("uq_dependencies_project_type_name", "project_id", "dep_type", func.lower(text("name")), unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    dep_type: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB)


class Rules(Base):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("project_id", postgresql_nulls_not_distinct=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # NULL = global rules
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    data: Mapped[dict] = mapped_column(JSONB)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index(
            "uq_tasks_one_running",
            "project_id",
            "kind",
            "target_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # running | done | error
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    result_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
