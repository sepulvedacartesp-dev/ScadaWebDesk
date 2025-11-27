from __future__ import annotations

import re
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ReportFrequency = Literal["daily", "weekly", "monthly"]
ReportStatus = Literal["idle", "queued", "running", "success", "failed", "skipped"]


def _normalize_time_of_day(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not match:
        raise ValueError("timeOfDay debe tener formato HH:MM")
    hours = int(match.group(1))
    minutes = int(match.group(2))
    if hours < 0 or hours > 23:
        raise ValueError("timeOfDay (hora) debe estar entre 0 y 23")
    if minutes < 0 or minutes > 59:
        raise ValueError("timeOfDay (minutos) debe estar entre 0 y 59")
    return f"{hours:02d}:{minutes:02d}"


class ReportBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=120)
    planta_id: str = Field(..., alias="plantaId")
    frequency: ReportFrequency
    recipients: List[EmailStr] = Field(default_factory=list, alias="recipients")
    tags: List[str] = Field(default_factory=list)
    include_alarms: bool = Field(default=False, alias="includeAlarms")
    send_email: bool = Field(default=True, alias="sendEmail")
    day_of_week: Optional[int] = Field(None, ge=1, le=7, alias="dayOfWeek")
    day_of_month: Optional[int] = Field(None, ge=1, le=31, alias="dayOfMonth")
    time_of_day: Optional[str] = Field("08:00", alias="timeOfDay")
    timezone: Optional[str] = Field(None, alias="timezone")
    slot: Optional[int] = Field(None, ge=1, le=2, alias="slot")
    active: bool = Field(default=True)

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre es obligatorio")
        return cleaned

    @field_validator("planta_id")
    @classmethod
    def _normalize_planta(cls, value: str) -> str:
        cleaned = str(value).strip().lower()
        if not cleaned:
            raise ValueError("plantaId es obligatorio")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: List[str]) -> List[str]:
        if not value:
            return []
        seen = set()
        normalized: List[str] = []
        for raw in value:
            tag = str(raw).strip()
            if not tag:
                continue
            lowered = tag.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(tag)
        return normalized

    @field_validator("recipients")
    @classmethod
    def _normalize_recipients(cls, value: List[EmailStr]) -> List[EmailStr]:
        if not value:
            raise ValueError("Debes indicar al menos un correo de destino")
        seen = set()
        normalized: List[EmailStr] = []
        for raw in value:
            email = str(raw).strip().lower()
            if not email:
                continue
            if email in seen:
                continue
            seen.add(email)
            normalized.append(email)
        return normalized

    @field_validator("time_of_day")
    @classmethod
    def _validate_time(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_time_of_day(value)

    @field_validator("day_of_week", "day_of_month", "frequency")
    @classmethod
    def _validate_schedule(cls, value, info):
        data = info.data
        frequency = data.get("frequency")
        day_of_week = data.get("day_of_week")
        day_of_month = data.get("day_of_month")
        if frequency == "weekly" and day_of_week is None:
            raise ValueError("Para frecuencia semanal debes definir dayOfWeek (1=lunes, 7=domingo)")
        if frequency == "monthly" and day_of_month is None:
            raise ValueError("Para frecuencia mensual debes definir dayOfMonth (1-31)")
        return value


class ReportCreatePayload(ReportBase):
    pass


class ReportUpdatePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    planta_id: Optional[str] = Field(None, alias="plantaId")
    frequency: Optional[ReportFrequency] = None
    recipients: Optional[List[EmailStr]] = Field(None, alias="recipients")
    tags: Optional[List[str]] = None
    include_alarms: Optional[bool] = Field(None, alias="includeAlarms")
    send_email: Optional[bool] = Field(None, alias="sendEmail")
    day_of_week: Optional[int] = Field(None, ge=1, le=7, alias="dayOfWeek")
    day_of_month: Optional[int] = Field(None, ge=1, le=31, alias="dayOfMonth")
    time_of_day: Optional[str] = Field(None, alias="timeOfDay")
    timezone: Optional[str] = Field(None, alias="timezone")
    slot: Optional[int] = Field(None, ge=1, le=2, alias="slot")
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _trim_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre no puede quedar vacio")
        return cleaned

    @field_validator("planta_id")
    @classmethod
    def _normalize_planta(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = str(value).strip().lower()
        if not cleaned:
            raise ValueError("plantaId es obligatorio")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        seen = set()
        normalized: List[str] = []
        for raw in value:
            tag = str(raw).strip()
            if not tag:
                continue
            lowered = tag.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(tag)
        return normalized

    @field_validator("recipients")
    @classmethod
    def _normalize_recipients(cls, value: Optional[List[EmailStr]]) -> Optional[List[EmailStr]]:
        if value is None:
            return None
        seen = set()
        normalized: List[EmailStr] = []
        for raw in value:
            email = str(raw).strip().lower()
            if not email:
                continue
            if email in seen:
                continue
            seen.add(email)
            normalized.append(email)
        if not normalized:
            raise ValueError("Debes indicar al menos un correo de destino")
        return normalized

    @field_validator("time_of_day")
    @classmethod
    def _validate_time(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_time_of_day(value)


class ReportDefinitionOut(ReportBase):
    id: int
    empresa_id: str = Field(..., alias="empresaId")
    last_run_at: Optional[datetime] = Field(None, alias="lastRunAt")
    next_run_at: Optional[datetime] = Field(None, alias="nextRunAt")
    last_status: Optional[ReportStatus] = Field(None, alias="lastStatus")
    last_error: Optional[str] = Field(None, alias="lastError")
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")


class ReportRunOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    report_id: int = Field(..., alias="reportId")
    empresa_id: str = Field(..., alias="empresaId")
    planta_id: str = Field(..., alias="plantaId")
    status: ReportStatus
    window_start: Optional[datetime] = Field(None, alias="windowStart")
    window_end: Optional[datetime] = Field(None, alias="windowEnd")
    started_at: datetime = Field(..., alias="startedAt")
    completed_at: Optional[datetime] = Field(None, alias="completedAt")
    error: Optional[str] = None
    send_email: bool = Field(default=True, alias="sendEmail")
    emails_sent: List[str] = Field(default_factory=list, alias="emailsSent")
    pdf_size_bytes: Optional[int] = Field(None, alias="pdfSizeBytes")
    pdf_mime: Optional[str] = Field(None, alias="pdfMime")
    triggered_by: Optional[str] = Field(None, alias="triggeredBy")


class ReportRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    window_start: Optional[datetime] = Field(None, alias="windowStart")
    window_end: Optional[datetime] = Field(None, alias="windowEnd")
    send_email: bool = Field(default=True, alias="sendEmail")

    @field_validator("window_end")
    @classmethod
    def _validate_range(cls, end: Optional[datetime], info):
        start = info.data.get("window_start")
        if start and end and start >= end:
            raise ValueError("windowEnd debe ser posterior a windowStart")
        return end
