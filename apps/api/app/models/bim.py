import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BimElement(Base):
    """One element of one revision. Rows are derived data and may be rebuilt by re-extraction."""

    __tablename__ = "bim_elements"
    __table_args__ = (
        UniqueConstraint("revision_id", "guid", name="uq_element_revision_guid"),
        Index("ix_elements_revision_class", "revision_id", "ifc_class"),
        Index("ix_elements_revision_level", "revision_id", "level"),
        Index("ix_elements_revision_tag", "revision_id", "tag"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    revision_id: Mapped[str] = mapped_column(ForeignKey("document_revisions.id", ondelete="CASCADE"))
    guid: Mapped[str] = mapped_column(String(64))
    ifc_class: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), default="")
    tag: Mapped[str] = mapped_column(String(64), default="")
    level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room: Mapped[str | None] = mapped_column(String(64), nullable=True)
    material: Mapped[str | None] = mapped_column(String(255), nullable=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    geometry: Mapped[dict] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64))
