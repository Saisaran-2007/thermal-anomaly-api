from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "warning_limit_C >= 0 AND critical_limit_C > warning_limit_C",
            name="ck_assets_temperature_limits",
        ),
    )

    asset_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    warning_limit_C: Mapped[float] = mapped_column(Float, nullable=False)
    critical_limit_C: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    inspections: Mapped[list["Inspection"]] = relationship(back_populates="asset")


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "timestamp",
            name="uq_inspections_asset_id_timestamp",
        ),
        CheckConstraint(
            "max_temp_C >= 0 AND mean_temp_C >= 0 AND max_temp_C >= mean_temp_C",
            name="ck_inspections_valid_temperatures",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("assets.asset_id"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    max_temp_C: Mapped[float] = mapped_column(Float, nullable=False)
    mean_temp_C: Mapped[float] = mapped_column(Float, nullable=False)
    image_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    asset: Mapped["Asset"] = relationship(back_populates="inspections")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="inspection")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('warning', 'critical')",
            name="ck_alerts_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged')",
            name="ck_alerts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inspections.id"),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
        server_default="open",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    inspection: Mapped["Inspection"] = relationship(back_populates="alerts")
    acknowledgement_history: Mapped[list["AlertAcknowledgementHistory"]] = (
        relationship(back_populates="alert")
    )


class AlertAcknowledgementHistory(Base):
    __tablename__ = "alert_acknowledgement_history"
    __table_args__ = (
        CheckConstraint(
            "previous_status = 'open' AND new_status = 'acknowledged'",
            name="ck_acknowledgement_status_transition",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alerts.id"),
        nullable=False,
        index=True,
    )
    acknowledged_by: Mapped[str] = mapped_column(String(255), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)

    alert: Mapped["Alert"] = relationship(back_populates="acknowledgement_history")
