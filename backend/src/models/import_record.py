import uuid
from datetime import datetime
from sqlalchemy import String, Text, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .common import now
from ..config.database import Base


class ImportRun(Base):
    """One import attempt against an existing batch (initial creation also gets one)."""
    __tablename__ = "import_runs"
    __table_args__ = (UniqueConstraint("batch_id", "idempotency_key", name="uq_import_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    source: Mapped[str] = mapped_column(String(20), default="initial")
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor: Mapped[str] = mapped_column(String(160), default="")
    total_rows: Mapped[int] = mapped_column(default=0)
    inserted_rows: Mapped[int] = mapped_column(default=0)
    duplicate_rows: Mapped[int] = mapped_column(default=0)
    quarantined_rows: Mapped[int] = mapped_column(default=0)
    conflict_rows: Mapped[int] = mapped_column(default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ImportRow(Base):
    """Per-row outcome: inserted / duplicate / quarantined, with the original line."""
    __tablename__ = "import_rows"
    __table_args__ = (UniqueConstraint("import_id", "line_no", name="uq_import_line"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_id: Mapped[str] = mapped_column(ForeignKey("import_runs.id"), index=True)
    line_no: Mapped[int]
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    # Parsed snapshot in cents, kept separately from the immutable raw source line.
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    existing_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)

    def to_dict(self):
        return {
            "line_no": self.line_no,
            "external_id": self.external_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "reasons": self.reasons or [],
            "raw_text": self.raw_text,
            "parsed": self.payload,
            "item_id": self.item_id,
            "existing_item_id": self.existing_item_id,
        }
