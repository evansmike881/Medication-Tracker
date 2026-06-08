"""Data models for Medication Tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(slots=True)
class DoseLog:
    """Recorded medication dose."""

    taken_at: datetime
    source: str = "manual"
    confirmed_by: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Serialize a dose log."""
        return {
            "taken_at": self.taken_at.isoformat(),
            "source": self.source,
            "confirmed_by": self.confirmed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DoseLog":
        """Create a dose log from storage data."""
        return cls(
            taken_at=datetime.fromisoformat(data["taken_at"]),
            source=data.get("source", "manual"),
            confirmed_by=data.get("confirmed_by"),
        )


@dataclass(slots=True)
class Medication:
    """Medication record."""

    medication_id: str
    profile_id: str
    profile_name: str
    name: str
    dosage: str
    schedules: list[str]
    quantity: float | None = None
    refill_at: float | None = None
    notes: str = ""
    instructions: str = ""
    purpose: str = ""
    form: str = ""
    strength_options: list[str] = field(default_factory=list)
    database_entry_id: str | None = None
    nfc_tag_id: str | None = None
    notification_enabled: bool = True
    notify_service: str | None = None
    caregiver_name: str | None = None
    caregiver_notify_service: str | None = None
    confirmation_required: bool = False
    reminder_minutes: int = 15
    missed_after_minutes: int = 60
    last_due_notification: str | None = None
    last_missed_notification: str | None = None
    last_refill_notification: str | None = None
    last_caregiver_notification: str | None = None
    start_date: date = field(default_factory=date.today)
    dose_logs: list[DoseLog] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialize a medication."""
        return {
            "medication_id": self.medication_id,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "name": self.name,
            "dosage": self.dosage,
            "schedules": self.schedules,
            "quantity": self.quantity,
            "refill_at": self.refill_at,
            "notes": self.notes,
            "instructions": self.instructions,
            "purpose": self.purpose,
            "form": self.form,
            "strength_options": self.strength_options,
            "database_entry_id": self.database_entry_id,
            "nfc_tag_id": self.nfc_tag_id,
            "notification_enabled": self.notification_enabled,
            "notify_service": self.notify_service,
            "caregiver_name": self.caregiver_name,
            "caregiver_notify_service": self.caregiver_notify_service,
            "confirmation_required": self.confirmation_required,
            "reminder_minutes": self.reminder_minutes,
            "missed_after_minutes": self.missed_after_minutes,
            "last_due_notification": self.last_due_notification,
            "last_missed_notification": self.last_missed_notification,
            "last_refill_notification": self.last_refill_notification,
            "last_caregiver_notification": self.last_caregiver_notification,
            "start_date": self.start_date.isoformat(),
            "dose_logs": [dose_log.as_dict() for dose_log in self.dose_logs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Medication":
        """Create a medication from storage data."""
        return cls(
            medication_id=data["medication_id"],
            profile_id=data["profile_id"],
            profile_name=data["profile_name"],
            name=data["name"],
            dosage=data["dosage"],
            schedules=list(data["schedules"]),
            quantity=data.get("quantity"),
            refill_at=data.get("refill_at"),
            notes=data.get("notes", ""),
            instructions=data.get("instructions", ""),
            purpose=data.get("purpose", ""),
            form=data.get("form", ""),
            strength_options=list(data.get("strength_options", [])),
            database_entry_id=data.get("database_entry_id"),
            nfc_tag_id=data.get("nfc_tag_id"),
            notification_enabled=data.get("notification_enabled", True),
            notify_service=data.get("notify_service"),
            caregiver_name=data.get("caregiver_name"),
            caregiver_notify_service=data.get("caregiver_notify_service"),
            confirmation_required=data.get("confirmation_required", False),
            reminder_minutes=data.get("reminder_minutes", 15),
            missed_after_minutes=data.get("missed_after_minutes", 60),
            last_due_notification=data.get("last_due_notification"),
            last_missed_notification=data.get("last_missed_notification"),
            last_refill_notification=data.get("last_refill_notification"),
            last_caregiver_notification=data.get("last_caregiver_notification"),
            start_date=date.fromisoformat(data["start_date"]),
            dose_logs=[DoseLog.from_dict(item) for item in data.get("dose_logs", [])],
        )
