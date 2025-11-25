from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


AlarmOperator = Literal["lte", "gte", "eq"]
AlarmValueType = Literal["number", "boolean"]


class AlarmRuleBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    tag: str = Field(..., min_length=1, max_length=255)
    planta_id: str = Field("default", alias="plantaId", min_length=0, max_length=255)
    operator: AlarmOperator
    threshold: float = Field(..., alias="threshold")
    value_type: AlarmValueType = Field(..., alias="valueType")
    notify_email: EmailStr = Field(..., alias="notifyEmail")
    cooldown_seconds: int = Field(300, alias="cooldownSeconds", ge=0, le=86400)
    active: bool = True

    @field_validator("threshold")
    @classmethod
    def validate_boolean_threshold(cls, value: float, info):
        value_type = info.data.get("value_type") or info.data.get("valueType")
        if value_type == "boolean" and value not in (0, 1):
            raise ValueError("Para variables booleanas, el umbral debe ser 0 o 1")
        return float(value)

    @field_validator("tag")
    @classmethod
    def normalize_tag(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El tag no puede ser vacio")
        return normalized

    @field_validator("planta_id")
    @classmethod
    def normalize_planta(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        return normalized or "default"


class AlarmRuleCreate(AlarmRuleBase):
    pass


class AlarmRuleUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    tag: Optional[str] = Field(None, min_length=1, max_length=255)
    planta_id: Optional[str] = Field(None, alias="plantaId", min_length=0, max_length=255)
    operator: Optional[AlarmOperator] = None
    threshold: Optional[float] = Field(None, alias="threshold")
    value_type: Optional[AlarmValueType] = Field(None, alias="valueType")
    notify_email: Optional[EmailStr] = Field(None, alias="notifyEmail")
    cooldown_seconds: Optional[int] = Field(None, alias="cooldownSeconds", ge=0, le=86400)
    active: Optional[bool] = None

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return value
        return float(value)

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("El tag no puede ser vacio")
        return normalized

    @field_validator("planta_id")
    @classmethod
    def normalize_planta(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        return normalized or "default"


class AlarmRuleOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    empresa_id: str = Field(alias="empresaId")
    planta_id: str = Field(alias="plantaId")
    tag: str
    operator: AlarmOperator
    threshold: float
    value_type: AlarmValueType = Field(alias="valueType")
    notify_email: EmailStr = Field(alias="notifyEmail")
    cooldown_seconds: int = Field(alias="cooldownSeconds")
    active: bool
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_triggered_at: Optional[datetime] = Field(None, alias="lastTriggeredAt")


class AlarmEventOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    rule_id: int = Field(alias="ruleId")
    empresa_id: str = Field(alias="empresaId")
    planta_id: str = Field(alias="plantaId")
    tag: str
    observed_value: float = Field(alias="observedValue")
    operator: AlarmOperator
    threshold_value: float = Field(alias="thresholdValue")
    email_sent: bool = Field(alias="emailSent")
    email_error: Optional[str] = Field(None, alias="emailError")
    triggered_at: datetime = Field(alias="triggeredAt")
    notified_at: Optional[datetime] = Field(None, alias="notifiedAt")
