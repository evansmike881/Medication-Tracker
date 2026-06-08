"""Medication business logic."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DEFAULT_MISSED_AFTER_MINUTES, DEFAULT_REMINDER_MINUTES
from .medication_database import MedicationDatabase
from .models import DoseLog, Medication
from .store import MedicationTrackerStore


class MedicationTrackerManager:
    """Manage medication records and dose calculations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.store = MedicationTrackerStore(hass)
        self.database = MedicationDatabase()
        self.medications: dict[str, Medication] = {}

    async def async_initialize(self) -> None:
        """Load persisted state."""
        self.medications = await self.store.async_load()

    async def async_add_medication(
        self,
        *,
        profile_id: str,
        profile_name: str,
        medication_id: str,
        medication_name: str,
        dosage: str,
        schedules: list[str],
        quantity: float | None = None,
        refill_at: float | None = None,
        notes: str = "",
        database_entry_id: str | None = None,
        nfc_tag_id: str | None = None,
        notification_enabled: bool = True,
        notify_service: str | None = None,
        reminder_minutes: int = DEFAULT_REMINDER_MINUTES,
        missed_after_minutes: int = DEFAULT_MISSED_AFTER_MINUTES,
    ) -> Medication:
        """Create or update a medication."""
        normalized_schedules = self._normalize_schedules(schedules)
        existing = self.medications.get(medication_id)
        medication = Medication(
            medication_id=medication_id,
            profile_id=profile_id,
            profile_name=profile_name,
            name=medication_name,
            dosage=dosage,
            schedules=normalized_schedules,
            quantity=float(quantity) if quantity is not None else None,
            refill_at=float(refill_at) if refill_at is not None else None,
            notes=notes,
            database_entry_id=database_entry_id,
            nfc_tag_id=nfc_tag_id or None,
            notification_enabled=notification_enabled,
            notify_service=notify_service or None,
            reminder_minutes=reminder_minutes,
            missed_after_minutes=missed_after_minutes,
            last_due_notification=existing.last_due_notification if existing else None,
            last_missed_notification=existing.last_missed_notification if existing else None,
            last_refill_notification=existing.last_refill_notification if existing else None,
            start_date=existing.start_date if existing else date.today(),
            dose_logs=list(existing.dose_logs) if existing else [],
        )
        self.medications[medication_id] = medication
        await self._async_save()
        return medication

    async def async_log_dose(
        self,
        medication_id: str,
        taken_at: datetime | None = None,
    ) -> Medication:
        """Log a dose for a medication."""
        medication = self._get_medication(medication_id)
        timestamp = taken_at or dt_util.now()
        if dt_util.is_naive(timestamp):
            timestamp = dt_util.as_local(dt_util.as_utc(timestamp))
        medication.dose_logs.append(DoseLog(taken_at=timestamp))
        medication.dose_logs.sort(key=lambda item: item.taken_at)

        if medication.quantity is not None:
            medication.quantity = max(medication.quantity - 1, 0)

        medication.last_due_notification = None
        medication.last_missed_notification = None
        await self._async_save()
        return medication

    async def async_refill_medication(self, medication_id: str, quantity: float) -> Medication:
        """Add remaining quantity."""
        medication = self._get_medication(medication_id)
        current_quantity = medication.quantity or 0
        medication.quantity = current_quantity + quantity
        await self._async_save()
        return medication

    async def async_remove_medication(self, medication_id: str) -> None:
        """Remove a medication."""
        self._get_medication(medication_id)
        self.medications.pop(medication_id)
        await self._async_save()

    def list_medications(self) -> Iterable[Medication]:
        """Return all medications."""
        return self.medications.values()

    def list_database_entries(self) -> list[dict[str, Any]]:
        """Return bundled medication catalog entries."""
        return self.database.list_entries()

    def get_database_entry(self, entry_id: str) -> dict[str, Any] | None:
        """Return one bundled medication entry."""
        return self.database.get(entry_id)

    def get_by_tag(self, tag_id: str) -> Medication | None:
        """Return a medication bound to an NFC tag."""
        for medication in self.medications.values():
            if medication.nfc_tag_id == tag_id:
                return medication
        return None

    def get_snapshot(self, medication_id: str) -> dict[str, Any]:
        """Return a computed status snapshot."""
        medication = self._get_medication(medication_id)
        now = dt_util.now()
        today = now.date()
        schedule_occurrences = self._scheduled_occurrences(medication, medication.start_date, today)
        matched_occurrences = self._matched_occurrences(medication, schedule_occurrences)
        past_due_today = [
            scheduled
            for scheduled in schedule_occurrences
            if scheduled.date() == today and scheduled <= now
        ]
        taken_today = [
            scheduled
            for scheduled in matched_occurrences
            if scheduled.date() == today and scheduled <= now
        ]
        last_dose = medication.dose_logs[-1].taken_at if medication.dose_logs else None
        next_dose = self._next_scheduled_dose(medication, now)
        missed_doses = self._missed_doses(medication, now, matched_occurrences)
        total_scheduled = len(schedule_occurrences)
        compliance = round((len(matched_occurrences) / total_scheduled) * 100, 1) if total_scheduled else 100.0
        days_remaining = self._days_remaining(medication)

        return {
            "medication_id": medication.medication_id,
            "profile_id": medication.profile_id,
            "profile_name": medication.profile_name,
            "medication_name": medication.name,
            "dosage": medication.dosage,
            "notes": medication.notes,
            "schedules": medication.schedules,
            "dose_count": len(medication.dose_logs),
            "last_taken": last_dose.isoformat() if last_dose else None,
            "next_dose": next_dose.isoformat() if next_dose else None,
            "missed_doses": missed_doses,
            "remaining_quantity": medication.quantity,
            "refill_at": medication.refill_at,
            "days_remaining": days_remaining,
            "compliance_percentage": compliance,
            "expected_doses_today": len(past_due_today),
            "taken_today": len(taken_today),
            "notification_enabled": medication.notification_enabled,
            "notify_service": medication.notify_service,
            "nfc_tag_id": medication.nfc_tag_id,
            "database_entry_id": medication.database_entry_id,
            "reminder_minutes": medication.reminder_minutes,
            "missed_after_minutes": medication.missed_after_minutes,
            "due_now": self._is_due_now(medication, now),
            "needs_refill": self._needs_refill(medication),
        }

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate dashboard values."""
        snapshots = [self.get_snapshot(medication.medication_id) for medication in self.medications.values()]
        next_due_candidates = [item["next_dose"] for item in snapshots if item["next_dose"]]
        return {
            "medication_count": len(snapshots),
            "due_now_count": sum(1 for item in snapshots if item["due_now"]),
            "missed_dose_count": sum(item["missed_doses"] for item in snapshots),
            "refill_needed_count": sum(1 for item in snapshots if item["needs_refill"]),
            "next_due": min(next_due_candidates) if next_due_candidates else None,
        }

    def get_pending_alerts(self) -> list[dict[str, Any]]:
        """Return due, missed, and refill alerts that still need notifying."""
        now = dt_util.now()
        alerts: list[dict[str, Any]] = []
        for medication in self.medications.values():
            if not medication.notification_enabled:
                continue

            due_schedule = self._current_due_schedule(medication, now)
            if due_schedule and medication.last_due_notification != due_schedule.isoformat():
                alerts.append(
                    {
                        "type": "due",
                        "medication_id": medication.medication_id,
                        "notify_service": medication.notify_service,
                        "scheduled_time": due_schedule,
                        "message": (
                            f"{medication.profile_name} is due to take {medication.name} "
                            f"({medication.dosage}) at {due_schedule.strftime('%H:%M')}."
                        ),
                    }
                )

            missed_schedule = self._current_missed_schedule(medication, now)
            if missed_schedule and medication.last_missed_notification != missed_schedule.isoformat():
                alerts.append(
                    {
                        "type": "missed",
                        "medication_id": medication.medication_id,
                        "notify_service": medication.notify_service,
                        "scheduled_time": missed_schedule,
                        "message": (
                            f"{medication.profile_name} missed the scheduled {medication.name} "
                            f"dose from {missed_schedule.strftime('%H:%M')}."
                        ),
                    }
                )

            if self._needs_refill(medication):
                refill_marker = date.today().isoformat()
                if medication.last_refill_notification != refill_marker:
                    remaining = medication.quantity if medication.quantity is not None else 0
                    alerts.append(
                        {
                            "type": "refill",
                            "medication_id": medication.medication_id,
                            "notify_service": medication.notify_service,
                            "scheduled_time": None,
                            "message": (
                                f"{medication.name} is running low with {remaining:g} doses remaining."
                            ),
                        }
                    )
        return alerts

    async def async_mark_alert_sent(
        self,
        medication_id: str,
        alert_type: str,
        scheduled_time: datetime | None = None,
    ) -> None:
        """Persist notification markers to avoid duplicate alerts."""
        medication = self._get_medication(medication_id)
        if alert_type == "due" and scheduled_time:
            medication.last_due_notification = scheduled_time.isoformat()
        elif alert_type == "missed" and scheduled_time:
            medication.last_missed_notification = scheduled_time.isoformat()
        elif alert_type == "refill":
            medication.last_refill_notification = date.today().isoformat()
        await self._async_save()

    async def _async_save(self) -> None:
        """Persist medication state."""
        await self.store.async_save(self.medications)

    def _get_medication(self, medication_id: str) -> Medication:
        """Fetch a medication or raise a service-friendly error."""
        try:
            return self.medications[medication_id]
        except KeyError as err:
            raise HomeAssistantError(f"Unknown medication_id: {medication_id}") from err

    def _normalize_schedules(self, schedules: list[str]) -> list[str]:
        """Normalize schedule strings."""
        normalized: set[str] = set()
        for value in schedules:
            try:
                parsed_time = time.fromisoformat(value)
            except ValueError as err:
                raise HomeAssistantError(
                    f"Invalid schedule time '{value}'. Use HH:MM or HH:MM:SS."
                ) from err
            normalized.add(parsed_time.strftime("%H:%M"))

        if not normalized:
            raise HomeAssistantError("At least one schedule time is required.")

        return sorted(normalized)

    def _combine(self, target_date: date, schedule: str) -> datetime:
        """Combine a date and schedule into a timezone-aware datetime."""
        scheduled_time = time.fromisoformat(schedule)
        return datetime.combine(target_date, scheduled_time, tzinfo=dt_util.DEFAULT_TIME_ZONE)

    def _next_scheduled_dose(self, medication: Medication, now: datetime) -> datetime | None:
        """Return the next scheduled dose datetime."""
        for day_offset in range(0, 8):
            candidate_date = now.date() + timedelta(days=day_offset)
            for schedule in medication.schedules:
                candidate = self._combine(candidate_date, schedule)
                if candidate > now:
                    return candidate
        return None

    def _days_remaining(self, medication: Medication) -> int | None:
        """Calculate how many days of medication remain."""
        if medication.quantity is None:
            return None

        daily_doses = len(medication.schedules)
        if daily_doses == 0:
            return None

        return math.floor(medication.quantity / daily_doses)

    def _current_due_schedule(self, medication: Medication, now: datetime) -> datetime | None:
        """Return the currently due schedule inside the reminder window."""
        matched_today = set(
            scheduled
            for scheduled in self._matched_occurrences(
                medication,
                [self._combine(now.date(), schedule) for schedule in medication.schedules],
            )
            if scheduled.date() == now.date()
        )
        for schedule in medication.schedules:
            scheduled_time = self._combine(now.date(), schedule)
            due_time = scheduled_time + timedelta(minutes=medication.reminder_minutes)
            if scheduled_time <= now <= due_time:
                if scheduled_time in matched_today:
                    continue
                return scheduled_time
        return None

    def _current_missed_schedule(self, medication: Medication, now: datetime) -> datetime | None:
        """Return a missed schedule once the overdue window has passed."""
        matched_today = set(
            scheduled
            for scheduled in self._matched_occurrences(
                medication,
                [self._combine(now.date(), schedule) for schedule in medication.schedules],
            )
            if scheduled.date() == now.date()
        )
        for schedule in medication.schedules:
            scheduled_time = self._combine(now.date(), schedule)
            missed_time = scheduled_time + timedelta(minutes=medication.missed_after_minutes)
            if now < missed_time:
                continue
            if scheduled_time in matched_today:
                continue
            return scheduled_time
        return None

    def _is_due_now(self, medication: Medication, now: datetime) -> bool:
        """Return whether a medication is inside its due window."""
        return self._current_due_schedule(medication, now) is not None

    def _needs_refill(self, medication: Medication) -> bool:
        """Return whether the medication has crossed the refill threshold."""
        if medication.quantity is None or medication.refill_at is None:
            return False
        return medication.quantity <= medication.refill_at

    def _scheduled_occurrences(self, medication: Medication, start_date: date, end_date: date) -> list[datetime]:
        """Return every scheduled occurrence in a date range."""
        occurrences: list[datetime] = []
        current_date = start_date
        while current_date <= end_date:
            for schedule in medication.schedules:
                occurrences.append(self._combine(current_date, schedule))
            current_date += timedelta(days=1)
        return sorted(occurrences)

    def _matched_occurrences(
        self,
        medication: Medication,
        occurrences: list[datetime],
    ) -> list[datetime]:
        """Greedily match dose logs to scheduled occurrences."""
        logs = [dt_util.as_local(dose_log.taken_at) for dose_log in medication.dose_logs]
        remaining_logs = sorted(logs)
        matched: list[datetime] = []
        for occurrence in sorted(occurrences):
            for index, logged_at in enumerate(remaining_logs):
                if logged_at.date() != occurrence.date():
                    continue
                if logged_at >= occurrence:
                    matched.append(occurrence)
                    remaining_logs.pop(index)
                    break
        return matched

    def _missed_doses(
        self,
        medication: Medication,
        now: datetime,
        matched_occurrences: list[datetime],
    ) -> int:
        """Count scheduled doses that have passed their missed threshold without a matching log."""
        missed = 0
        matched_set = set(matched_occurrences)
        for occurrence in self._scheduled_occurrences(medication, medication.start_date, now.date()):
            if occurrence in matched_set:
                continue
            if now >= occurrence + timedelta(minutes=medication.missed_after_minutes):
                missed += 1
        return missed
