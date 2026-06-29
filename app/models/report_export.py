from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, CheckConstraint, Date, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EmailStatus, ReportExportStatus
from app.db.base import Base
from app.utils.uuid import generate_uuid4

if TYPE_CHECKING:
    from app.models.driver_profile import DriverProfile


class ReportExport(Base):
    __tablename__ = "report_exports"
    __table_args__ = (
        CheckConstraint(
            "period_type IN ('WEEKLY', 'MONTHLY', 'CUSTOM')",
            name="ck_report_exports_period_type",
        ),
        CheckConstraint(
            "export_status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')",
            name="ck_report_exports_export_status",
        ),
        CheckConstraint(
            "email_status IN ('NOT_REQUESTED', 'PENDING', 'SENT', 'FAILED')",
            name="ck_report_exports_email_status",
        ),
        CheckConstraint(
            "failure_stage IS NULL OR failure_stage IN ('EXPORT', 'EMAIL')",
            name="ck_report_exports_failure_stage",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_report_exports_period_end_after_start",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_report_exports_completed_at_after_created_at",
        ),
        CheckConstraint(
            "emailed_at IS NULL OR emailed_at >= created_at",
            name="ck_report_exports_emailed_at_after_created_at",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at >= created_at",
            name="ck_report_exports_expires_at_after_created_at",
        ),
        CheckConstraint(
            "email_status = 'NOT_REQUESTED' OR recipient_email IS NOT NULL",
            name="ck_report_exports_email_requires_recipient",
        ),
        Index("idx_report_exports_profile_created_at", "profile_id", text("created_at DESC")),
        Index("idx_report_exports_export_status", "export_status"),
        Index("idx_report_exports_email_status", "email_status"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_ai_ci",
        },
    )

    id: Mapped[str] = mapped_column(
        CHAR(36),
        primary_key=True,
        nullable=False,
        default=generate_uuid4,
    )
    profile_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey(
            "driver_profiles.id",
            name="fk_report_exports_profile_id_driver_profiles",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        nullable=False,
    )
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filter_options_json: Mapped[dict[str, Any]] = mapped_column(
        mysql.JSON,
        nullable=False,
        default=dict,
    )
    export_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReportExportStatus.PENDING.value,
        server_default=text("'PENDING'"),
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EmailStatus.NOT_REQUESTED.value,
        server_default=text("'NOT_REQUESTED'"),
    )
    failure_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        mysql.DATETIME(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    emailed_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)

    profile: Mapped[DriverProfile] = relationship(
        "DriverProfile",
        back_populates="report_exports",
    )
