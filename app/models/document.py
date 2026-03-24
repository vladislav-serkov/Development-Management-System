from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, default=0)

    features: Mapped[list["Feature"]] = relationship(
        "Feature",
        back_populates="document",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename} status={self.status}>"


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dependencies_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_logic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="detected")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    overview_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="features")

    def __repr__(self) -> str:
        return f"<Feature id={self.id} name={self.name} type={self.type} status={self.status}>"
