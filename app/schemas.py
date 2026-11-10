from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssetCreate(BaseModel):
    """Fields required to register a monitored asset."""

    asset_id: str = Field(description="Unique identifier for the asset.")
    name: str = Field(description="Human-readable asset name.")
    type: str = Field(description="Kind of equipment, such as a boiler or motor.")
    location: str = Field(description="Where the asset is located.")
    warning_limit_C: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive temperature at which a warning should be raised.",
    )
    critical_limit_C: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="Positive temperature at which a critical alert should be raised.",
    )

    @field_validator("asset_id", "name", "type", "location")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be empty.")
        return value

    @model_validator(mode="after")
    def critical_limit_must_be_higher(self) -> Self:
        if self.critical_limit_C <= self.warning_limit_C:
            raise ValueError("critical_limit_C must be greater than warning_limit_C.")
        return self


class AssetResponse(BaseModel):
    """Asset information returned by the API, including its creation time."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: str = Field(description="Unique identifier for the asset.")
    name: str = Field(description="Human-readable asset name.")
    type: str = Field(description="Kind of equipment.")
    location: str = Field(description="Where the asset is located.")
    warning_limit_C: float = Field(description="Warning temperature limit.")
    critical_limit_C: float = Field(description="Critical temperature limit.")
    created_at: datetime = Field(description="When the asset record was created.")


class InspectionCreate(BaseModel):
    """Fields required to record an inspection."""

    asset_id: str = Field(description="Identifier of the inspected asset.")
    timestamp: datetime = Field(description="Date and time when the inspection occurred.")
    max_temp_C: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Highest temperature measured, in degrees Celsius.",
    )
    mean_temp_C: float = Field(
        ge=0,
        allow_inf_nan=False,
        description="Average temperature measured, in degrees Celsius.",
    )
    image_ref: str = Field(description="Reference to the inspection image or data.")

    @field_validator("asset_id", "image_ref")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be empty.")
        return value

    @model_validator(mode="after")
    def mean_must_not_exceed_max(self) -> Self:
        if self.mean_temp_C > self.max_temp_C:
            raise ValueError("mean_temp_C must not exceed max_temp_C.")
        return self


class InspectionResponse(BaseModel):
    """Stored inspection information returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Database-generated inspection identifier.")
    asset_id: str = Field(description="Identifier of the inspected asset.")
    timestamp: datetime = Field(description="Date and time when the inspection occurred.")
    max_temp_C: float = Field(description="Highest temperature measured.")
    mean_temp_C: float = Field(description="Average temperature measured.")
    image_ref: str = Field(description="Reference to the inspection image or data.")
    created_at: datetime = Field(description="When the inspection record was created.")


class AlertResponse(BaseModel):
    """Alert information returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Database-generated alert identifier.")
    inspection_id: int = Field(description="Identifier of the related inspection.")
    severity: Literal["warning", "critical"] = Field(
        description="Alert severity: warning or critical."
    )
    status: Literal["open", "acknowledged"] = Field(
        description="Alert status: open or acknowledged."
    )
    created_at: datetime = Field(description="When the alert was created.")


class OpenAlertResponse(AlertResponse):
    """Open alert details with its asset and inspection temperatures."""

    asset_id: str = Field(description="Identifier of the asset related to the alert.")
    max_temp_C: float = Field(description="Highest temperature recorded by the inspection.")
    mean_temp_C: float = Field(description="Average temperature recorded by the inspection.")


class AcknowledgementCreate(BaseModel):
    """Fields required to acknowledge an alert."""

    acknowledged_by: str = Field(description="Name or identifier of the person acknowledging.")

    @field_validator("acknowledged_by")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("acknowledged_by must not be empty.")
        return value


class AcknowledgementResponse(BaseModel):
    """Stored record of who acknowledged an alert and its status change."""

    model_config = ConfigDict(from_attributes=True)

    alert_id: int = Field(description="Identifier of the acknowledged alert.")
    acknowledged_by: str = Field(description="Name or identifier of the person acknowledging.")
    acknowledged_at: datetime = Field(description="When the alert was acknowledged.")
    previous_status: Literal["open"] = Field(
        description="Alert status before acknowledgement."
    )
    new_status: Literal["acknowledged"] = Field(
        description="Alert status after acknowledgement."
    )
