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
    taken_by: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Serialize a dose log."""
        return {
            "taken_at": self.taken_at.isoformat(),
            "source": self.source,
            "confirmed_by": self.confirmed_by,
            "taken_by": self.taken_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DoseLog":
        """Create a dose log from storage data."""
        return cls(
            taken_at=datetime.fromisoformat(data["taken_at"]),
            source=data.get("source", "manual"),
            confirmed_by=data.get("confirmed_by"),
            taken_by=data.get("taken_by"),
        )


@dataclass(slots=True)
class Group:
    """A named set of medications taken together (one schedule, one notification)."""

    group_id: str
    profile_id: str
    profile_name: str
    name: str
    schedules: list[str]
    days_of_week: list[int] | None = None
    interval_days: int = 1
    anchor_date: date | None = None
    notify_service: str | None = None
    nfc_tag_id: str | None = None
    notification_enabled: bool = True
    order: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Serialize a group."""
        return {
            "group_id": self.group_id,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "name": self.name,
            "schedules": self.schedules,
            "days_of_week": self.days_of_week,
            "interval_days": self.interval_days,
            "anchor_date": self.anchor_date.isoformat() if self.anchor_date else None,
            "notify_service": self.notify_service,
            "nfc_tag_id": self.nfc_tag_id,
            "notification_enabled": self.notification_enabled,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Group":
        """Create a group from storage data."""
        return cls(
            group_id=data["group_id"],
            profile_id=data["profile_id"],
            profile_name=data["profile_name"],
            name=data["name"],
            schedules=list(data.get("schedules", [])),
            days_of_week=(
                sorted({int(day) for day in data["days_of_week"]}) if data.get("days_of_week") else None
            ),
            interval_days=max(int(data.get("interval_days", 1) or 1), 1),
            anchor_date=date.fromisoformat(data["anchor_date"]) if data.get("anchor_date") else None,
            notify_service=data.get("notify_service"),
            nfc_tag_id=data.get("nfc_tag_id"),
            notification_enabled=bool(data.get("notification_enabled", True)),
            order=int(data.get("order", 0) or 0),
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
    duplicate_guard_minutes: int = 0
    repeat_every_minutes: int = 5
    max_repeats: int = 2
    days_of_week: list[int] | None = None
    end_date: date | None = None
    as_needed: bool = False
    max_doses_per_day: int | None = None
    interval_days: int = 1
    anchor_date: date | None = None
    escalate_after_minutes: int = 0
    last_escalation_notification: str | None = None
    group_id: str | None = None
    sort_order: int = 0
    food_note: str = ""
    keep_apart: list[str] = field(default_factory=list)
    keep_apart_minutes: int = 120
    created_at: str | None = None
    last_due_sent_at: str | None = None
    due_repeat_count: int = 0
    last_due_notification: str | None = None
    last_missed_notification: str | None = None
    last_refill_notification: str | None = None
    last_caregiver_notification: str | None = None
    snoozed_until: str | None = None
    skipped_occurrences: list[str] = field(default_factory=list)
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
            "duplicate_guard_minutes": self.duplicate_guard_minutes,
            "repeat_every_minutes": self.repeat_every_minutes,
            "max_repeats": self.max_repeats,
            "days_of_week": self.days_of_week,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "as_needed": self.as_needed,
            "max_doses_per_day": self.max_doses_per_day,
            "interval_days": self.interval_days,
            "anchor_date": self.anchor_date.isoformat() if self.anchor_date else None,
            "escalate_after_minutes": self.escalate_after_minutes,
            "last_escalation_notification": self.last_escalation_notification,
            "group_id": self.group_id,
            "sort_order": self.sort_order,
            "food_note": self.food_note,
            "keep_apart": self.keep_apart,
            "keep_apart_minutes": self.keep_apart_minutes,
            "created_at": self.created_at,
            "last_due_sent_at": self.last_due_sent_at,
            "due_repeat_count": self.due_repeat_count,
            "last_due_notification": self.last_due_notification,
            "last_missed_notification": self.last_missed_notification,
            "last_refill_notification": self.last_refill_notification,
            "last_caregiver_notification": self.last_caregiver_notification,
            "snoozed_until": self.snoozed_until,
            "skipped_occurrences": self.skipped_occurrences,
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
            duplicate_guard_minutes=data.get("duplicate_guard_minutes", 0),
            repeat_every_minutes=data.get("repeat_every_minutes", 5),
            max_repeats=data.get("max_repeats", 2),
            days_of_week=(
                sorted({int(day) for day in data["days_of_week"]})
                if data.get("days_of_week")
                else None
            ),
            end_date=date.fromisoformat(data["end_date"]) if data.get("end_date") else None,
            as_needed=bool(data.get("as_needed", False)),
            max_doses_per_day=data.get("max_doses_per_day"),
            interval_days=max(int(data.get("interval_days", 1) or 1), 1),
            anchor_date=date.fromisoformat(data["anchor_date"]) if data.get("anchor_date") else None,
            escalate_after_minutes=int(data.get("escalate_after_minutes", 0) or 0),
            last_escalation_notification=data.get("last_escalation_notification"),
            group_id=data.get("group_id"),
            sort_order=int(data.get("sort_order", 0) or 0),
            food_note=data.get("food_note", "") or "",
            keep_apart=list(data.get("keep_apart", []) or []),
            keep_apart_minutes=int(data.get("keep_apart_minutes", 120) or 120),
            created_at=data.get("created_at"),
            last_due_sent_at=data.get("last_due_sent_at"),
            due_repeat_count=data.get("due_repeat_count", 0),
            last_due_notification=data.get("last_due_notification"),
            last_missed_notification=data.get("last_missed_notification"),
            last_refill_notification=data.get("last_refill_notification"),
            last_caregiver_notification=data.get("last_caregiver_notification"),
            snoozed_until=data.get("snoozed_until"),
            skipped_occurrences=list(data.get("skipped_occurrences", [])),
            start_date=date.fromisoformat(data["start_date"]),
            dose_logs=[DoseLog.from_dict(item) for item in data.get("dose_logs", [])],
        )
