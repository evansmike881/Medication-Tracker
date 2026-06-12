"""Medication business logic."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

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
        self.database = await MedicationDatabase.async_load(self.hass)
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
        instructions: str = "",
        purpose: str = "",
        form: str = "",
        strength_options: list[str] | None = None,
        database_entry_id: str | None = None,
        nfc_tag_id: str | None = None,
        notification_enabled: bool = True,
        notify_service: str | None = None,
        caregiver_name: str | None = None,
        caregiver_notify_service: str | None = None,
        confirmation_required: bool = False,
        reminder_minutes: int = DEFAULT_REMINDER_MINUTES,
        missed_after_minutes: int = DEFAULT_MISSED_AFTER_MINUTES,
        duplicate_guard_minutes: int = 0,
    ) -> Medication:
        """Create or update a medication."""
        normalized_schedules = self._normalize_schedules(schedules)
        existing = self.medications.get(medication_id)
        database_entry = self.database.get(database_entry_id) if database_entry_id else None
        computed_purpose = purpose or (database_entry.get("purpose", "") if database_entry else "")
        computed_form = form or (database_entry.get("form", "") if database_entry else "")
        computed_instructions = instructions or (database_entry.get("instructions", "") if database_entry else "")
        computed_strength_options = (
            list(strength_options)
            if strength_options is not None
            else list(database_entry.get("strength_options", [])) if database_entry else []
        )
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
            instructions=computed_instructions,
            purpose=computed_purpose,
            form=computed_form,
            strength_options=computed_strength_options,
            database_entry_id=database_entry_id,
            nfc_tag_id=nfc_tag_id or None,
            notification_enabled=notification_enabled,
            notify_service=notify_service or None,
            caregiver_name=caregiver_name or (existing.caregiver_name if existing else None),
            caregiver_notify_service=caregiver_notify_service or (existing.caregiver_notify_service if existing else None),
            confirmation_required=confirmation_required,
            reminder_minutes=reminder_minutes,
            missed_after_minutes=missed_after_minutes,
            duplicate_guard_minutes=duplicate_guard_minutes,
            last_due_notification=existing.last_due_notification if existing else None,
            last_missed_notification=existing.last_missed_notification if existing else None,
            last_refill_notification=existing.last_refill_notification if existing else None,
            last_caregiver_notification=existing.last_caregiver_notification if existing else None,
            snoozed_until=existing.snoozed_until if existing else None,
            skipped_occurrences=list(existing.skipped_occurrences) if existing else [],
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
        source: str = "manual",
        confirmed_by: str | None = None,
        allow_duplicate: bool = False,
    ) -> Medication:
        """Log a dose for a medication."""
        medication = self._get_medication(medication_id)
        timestamp = taken_at or dt_util.now()
        if _is_naive_datetime(timestamp):
            timestamp = dt_util.as_local(dt_util.as_utc(timestamp))
        if not allow_duplicate:
            self._validate_duplicate_guard(medication, timestamp)
        medication.dose_logs.append(
            DoseLog(
                taken_at=timestamp,
                source=source,
                confirmed_by=confirmed_by,
            )
        )
        medication.dose_logs.sort(key=lambda item: item.taken_at)

        if medication.quantity is not None:
            medication.quantity = max(medication.quantity - 1, 0)

        medication.last_due_notification = None
        medication.last_missed_notification = None
        medication.last_caregiver_notification = None
        medication.snoozed_until = None
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

    async def async_snooze_medication(self, medication_id: str, minutes: int) -> Medication:
        """Snooze a medication reminder for a number of minutes."""
        medication = self._get_medication(medication_id)
        medication.snoozed_until = (dt_util.now() + timedelta(minutes=minutes)).isoformat()
        medication.last_due_notification = None
        await self._async_save()
        return medication

    async def async_skip_medication_occurrence(
        self,
        medication_id: str,
        scheduled_time: datetime | None = None,
    ) -> Medication:
        """Skip the next or supplied scheduled occurrence for a medication."""
        medication = self._get_medication(medication_id)
        occurrence = scheduled_time or self._current_due_schedule(medication, dt_util.now()) or self._next_scheduled_dose(
            medication,
            dt_util.now(),
        )
        if occurrence is None:
            raise HomeAssistantError("No scheduled occurrence is available to skip.")

        occurrence_marker = occurrence.isoformat()
        if occurrence_marker not in medication.skipped_occurrences:
            medication.skipped_occurrences.append(occurrence_marker)
            medication.skipped_occurrences.sort()
        medication.last_due_notification = occurrence_marker
        medication.last_missed_notification = occurrence_marker
        medication.snoozed_until = None
        await self._async_save()
        return medication

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
        schedule_occurrences = [
            occurrence
            for occurrence in self._scheduled_occurrences(medication, medication.start_date, today)
            if occurrence.isoformat() not in medication.skipped_occurrences
        ]
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
        last_confirmed_by = medication.dose_logs[-1].confirmed_by if medication.dose_logs else None
        next_dose = self._next_scheduled_dose(medication, now)
        missed_doses = self._missed_doses(medication, now, matched_occurrences)
        total_scheduled = len(schedule_occurrences)
        compliance = round((len(matched_occurrences) / total_scheduled) * 100, 1) if total_scheduled else 100.0
        days_remaining = self._days_remaining(medication)
        caregiver_confirmation_needed = bool(
            medication.confirmation_required
            and medication.caregiver_name
            and medication.dose_logs
            and not medication.dose_logs[-1].confirmed_by
        )
        stock_depletion_date = self._stock_depletion_date(medication, now)
        snoozed_until = self._active_snoozed_until(medication, now)
        duplicate_dose_warning = self._duplicate_dose_warning(medication, now)

        return {
            "medication_id": medication.medication_id,
            "profile_id": medication.profile_id,
            "profile_name": medication.profile_name,
            "belongs_to": medication.profile_name,
            "medication_name": medication.name,
            "dosage": medication.dosage,
            "notes": medication.notes,
            "instructions": medication.instructions,
            "purpose": medication.purpose,
            "form": medication.form,
            "strength_options": medication.strength_options,
            "schedules": medication.schedules,
            "dose_count": len(medication.dose_logs),
            "last_taken": last_dose.isoformat() if last_dose else None,
            "last_confirmed_by": last_confirmed_by,
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
            "caregiver_name": medication.caregiver_name,
            "caregiver_notify_service": medication.caregiver_notify_service,
            "confirmation_required": medication.confirmation_required,
            "caregiver_confirmation_needed": caregiver_confirmation_needed,
            "nfc_tag_id": medication.nfc_tag_id,
            "database_entry_id": medication.database_entry_id,
            "reminder_minutes": medication.reminder_minutes,
            "missed_after_minutes": medication.missed_after_minutes,
            "duplicate_guard_minutes": medication.duplicate_guard_minutes,
            "duplicate_dose_warning": duplicate_dose_warning,
            "snoozed_until": snoozed_until.isoformat() if snoozed_until else None,
            "skipped_occurrences": medication.skipped_occurrences,
            "stock_depletion_date": stock_depletion_date.isoformat() if stock_depletion_date else None,
            "stock_status": self._stock_status(medication, now, stock_depletion_date),
            "due_now": self._is_due_now(medication, now),
            "needs_refill": self._needs_refill(medication),
        }

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate dashboard values."""
        snapshots = [self.get_snapshot(medication.medication_id) for medication in self.medications.values()]
        next_due_candidates = [item["next_dose"] for item in snapshots if item["next_dose"]]
        medications = list(self.medications.values())
        profile_names = sorted({medication.profile_name for medication in medications})
        caregiver_names = sorted({medication.caregiver_name for medication in medications if medication.caregiver_name})
        return {
            "medication_count": len(snapshots),
            "tracked_medications": ", ".join(medication.name for medication in medications) or "None",
            "tracked_profiles": ", ".join(profile_names) or "None",
            "tracked_caregivers": ", ".join(caregiver_names) or "None",
            "medication_registry": len(medications),
            "due_now_count": sum(1 for item in snapshots if item["due_now"]),
            "missed_dose_count": sum(item["missed_doses"] for item in snapshots),
            "refill_needed_count": sum(1 for item in snapshots if item["needs_refill"]),
            "caregiver_confirmation_count": sum(
                1 for item in snapshots if item["caregiver_confirmation_needed"]
            ),
            "next_due": min(next_due_candidates) if next_due_candidates else None,
        }

    def get_registry_rows(self) -> list[dict[str, Any]]:
        """Return medication rows for dashboard registry views."""
        rows: list[dict[str, Any]] = []
        now = dt_util.now()
        for medication in sorted(self.medications.values(), key=lambda item: (item.profile_name.lower(), item.name.lower())):
            snapshot = self.get_snapshot(medication.medication_id)
            entity_base = slugify(medication.name)
            status = self._current_display_status(medication, now)
            if status == "On Track" and snapshot["needs_refill"]:
                status = "Needs Refill"

            rows.append(
                {
                    "profile_name": medication.profile_name,
                    "medication_name": medication.name,
                    "medication_id": medication.medication_id,
                    "dosage": medication.dosage,
                    "purpose": snapshot["purpose"],
                    "form": snapshot["form"],
                    "instructions": snapshot["instructions"],
                    "schedules": medication.schedules,
                    "next_dose": snapshot["next_dose"],
                    "last_taken": snapshot["last_taken"],
                    "last_confirmed_by": snapshot["last_confirmed_by"],
                    "status": status,
                    "missed_doses": snapshot["missed_doses"],
                    "days_remaining": snapshot["days_remaining"],
                    "remaining_quantity": snapshot["remaining_quantity"],
                    "stock_depletion_date": snapshot["stock_depletion_date"],
                    "stock_status": snapshot["stock_status"],
                    "due_now": snapshot["due_now"],
                    "needs_refill": snapshot["needs_refill"],
                    "caregiver_name": snapshot["caregiver_name"],
                    "caregiver_confirmation_needed": snapshot["caregiver_confirmation_needed"],
                    "snoozed_until": snapshot["snoozed_until"],
                    "duplicate_dose_warning": snapshot["duplicate_dose_warning"],
                    "compliance_percentage": snapshot["compliance_percentage"],
                    "schedule_statuses": self._schedule_statuses(medication, now),
                    "button_entity_id": f"button.{entity_base}_log_dose",
                    "skip_button_entity_id": f"button.{entity_base}_skip_dose",
                    "snooze_button_entity_id": f"button.{entity_base}_snooze_10_minutes",
                    "next_dose_entity_id": f"sensor.{entity_base}_next_dose",
                    "last_dose_entity_id": f"sensor.{entity_base}_last_dose",
                    "snoozed_until_entity_id": f"sensor.{entity_base}_snoozed_until",
                    "stock_depletion_entity_id": f"sensor.{entity_base}_stock_depletion",
                    "due_now_entity_id": f"binary_sensor.{entity_base}_due_now",
                    "needs_refill_entity_id": f"binary_sensor.{entity_base}_needs_refill",
                }
            )

        return rows

    def get_pending_alerts(self) -> list[dict[str, Any]]:
        """Return due, missed, and refill alerts that still need notifying."""
        now = dt_util.now()
        alerts: list[dict[str, Any]] = []
        due_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        missed_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        refill_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        caregiver_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        for medication in self.medications.values():
            if not medication.notification_enabled:
                continue

            due_schedule = self._current_due_schedule(medication, now)
            if due_schedule and medication.last_due_notification != due_schedule.isoformat():
                due_alert_groups[
                    (
                        medication.profile_id,
                        due_schedule.isoformat(),
                        medication.notify_service,
                    )
                ].append(
                    {
                        "medication_id": medication.medication_id,
                        "profile_name": medication.profile_name,
                        "medication_name": medication.name,
                        "dosage": medication.dosage,
                        "notify_service": medication.notify_service,
                        "scheduled_time": due_schedule,
                        "display_time": self._effective_due_start(medication, due_schedule),
                    }
                )

            missed_schedule = self._current_missed_schedule(medication, now)
            if missed_schedule and medication.last_missed_notification != missed_schedule.isoformat():
                missed_alert_groups[
                    (
                        medication.profile_id,
                        missed_schedule.isoformat(),
                        medication.notify_service,
                    )
                ].append(
                    {
                        "medication_id": medication.medication_id,
                        "profile_name": medication.profile_name,
                        "medication_name": medication.name,
                        "dosage": medication.dosage,
                        "notify_service": medication.notify_service,
                        "scheduled_time": missed_schedule,
                    }
                )

            if self._needs_refill(medication):
                refill_marker = date.today().isoformat()
                if medication.last_refill_notification != refill_marker:
                    remaining = medication.quantity if medication.quantity is not None else 0
                    refill_alert_groups[
                        (
                            medication.profile_id,
                            refill_marker,
                            medication.notify_service,
                        )
                    ].append(
                        {
                            "medication_id": medication.medication_id,
                            "profile_name": medication.profile_name,
                            "medication_name": medication.name,
                            "dosage": medication.dosage,
                            "remaining": remaining,
                            "notify_service": medication.notify_service,
                            "scheduled_time": None,
                        }
                    )
            if medication.confirmation_required and medication.caregiver_name and medication.dose_logs:
                latest_log = medication.dose_logs[-1]
                if (
                    latest_log.confirmed_by is None
                    and medication.last_caregiver_notification != latest_log.taken_at.isoformat()
                ):
                    caregiver_alert_groups[
                        (
                            medication.profile_id,
                            latest_log.taken_at.isoformat(),
                            medication.caregiver_notify_service or medication.notify_service,
                        )
                    ].append(
                        {
                            "medication_id": medication.medication_id,
                            "profile_name": medication.profile_name,
                            "medication_name": medication.name,
                            "dosage": medication.dosage,
                            "caregiver_name": medication.caregiver_name,
                            "notify_service": medication.caregiver_notify_service or medication.notify_service,
                            "scheduled_time": latest_log.taken_at,
                        }
                    )
        for grouped_due_medications in due_alert_groups.values():
            alerts.append(self._build_due_alert(grouped_due_medications))
        for grouped_missed_medications in missed_alert_groups.values():
            alerts.append(self._build_missed_alert(grouped_missed_medications))
        for grouped_refill_medications in refill_alert_groups.values():
            alerts.append(self._build_refill_alert(grouped_refill_medications))
        for grouped_caregiver_medications in caregiver_alert_groups.values():
            alerts.append(self._build_caregiver_alert(grouped_caregiver_medications))

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
        elif alert_type == "caregiver_confirmation" and scheduled_time:
            medication.last_caregiver_notification = scheduled_time.isoformat()
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
                if candidate.isoformat() in medication.skipped_occurrences:
                    continue
                effective_due_start = self._effective_due_start(medication, candidate)
                if effective_due_start > now:
                    return effective_due_start
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
            if scheduled_time.isoformat() in medication.skipped_occurrences:
                continue
            effective_due_start = self._effective_due_start(medication, scheduled_time)
            due_time = effective_due_start + timedelta(minutes=medication.reminder_minutes)
            if effective_due_start <= now <= due_time:
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
            if scheduled_time.isoformat() in medication.skipped_occurrences:
                continue
            effective_due_start = self._effective_due_start(medication, scheduled_time)
            missed_time = effective_due_start + timedelta(minutes=medication.missed_after_minutes)
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
            if occurrence.isoformat() in medication.skipped_occurrences:
                continue
            effective_due_start = self._effective_due_start(medication, occurrence)
            if now >= effective_due_start + timedelta(minutes=medication.missed_after_minutes):
                missed += 1
        return missed

    def _schedule_statuses(self, medication: Medication, now: datetime, days_ahead: int = 30) -> dict[str, str]:
        """Return day-and-time specific statuses for upcoming scheduled doses."""
        end_date = now.date() + timedelta(days=max(days_ahead - 1, 0))
        occurrences = self._scheduled_occurrences(medication, now.date(), end_date)
        matched_occurrences = set(self._matched_occurrences(medication, occurrences))
        statuses: dict[str, str] = {}

        for occurrence in occurrences:
            occurrence_key = occurrence.strftime("%Y-%m-%dT%H:%M")
            if occurrence.isoformat() in medication.skipped_occurrences:
                statuses[occurrence_key] = "Skipped"
                continue
            if occurrence in matched_occurrences:
                statuses[occurrence_key] = "Taken"
                continue

            effective_due_start = self._effective_due_start(medication, occurrence)

            if now >= effective_due_start + timedelta(minutes=medication.missed_after_minutes):
                statuses[occurrence_key] = "Missed Dose"
                continue

            if occurrence <= now < effective_due_start:
                statuses[occurrence_key] = "Snoozed"
                continue

            if effective_due_start <= now <= effective_due_start + timedelta(minutes=medication.reminder_minutes):
                statuses[occurrence_key] = "Due Now"
                continue

            statuses[occurrence_key] = "On Track"

        return statuses

    def _current_display_status(self, medication: Medication, now: datetime) -> str:
        """Return a card-friendly status based on today's scheduled doses."""
        today_occurrences = self._scheduled_occurrences(medication, now.date(), now.date())
        if not today_occurrences:
            return "On Track"

        matched_today = set(self._matched_occurrences(medication, today_occurrences))
        has_taken_today = False

        for occurrence in today_occurrences:
            if occurrence in matched_today:
                has_taken_today = True
                continue

            if occurrence.isoformat() in medication.skipped_occurrences:
                continue

            effective_due_start = self._effective_due_start(medication, occurrence)

            if now >= effective_due_start + timedelta(minutes=medication.missed_after_minutes):
                return "Missed Dose"

            if occurrence <= now < effective_due_start:
                return "Snoozed"

            if effective_due_start <= now <= effective_due_start + timedelta(minutes=medication.reminder_minutes):
                return "Due Now"

        if has_taken_today:
            return "Taken"

        return "On Track"

    def _build_due_alert(self, due_medications: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a single due alert for one medication or a grouped set."""
        sorted_due_medications = sorted(
            due_medications,
            key=lambda item: (item["scheduled_time"], item["medication_name"].lower(), item["medication_id"]),
        )
        first = sorted_due_medications[0]
        medication_ids = [item["medication_id"] for item in sorted_due_medications]
        scheduled_time = first["scheduled_time"]
        display_time = first.get("display_time", scheduled_time)

        if len(sorted_due_medications) == 1:
            message = (
                f"{first['profile_name']} is due to take {first['medication_name']} "
                f"({first['dosage']}) at {display_time.strftime('%H:%M')}."
            )
        else:
            medication_lines = "\n".join(
                f"- {item['medication_name']} ({item['dosage']})"
                for item in sorted_due_medications
            )
            message = (
                f"{first['profile_name']} is due to take {len(sorted_due_medications)} medications "
                f"at {display_time.strftime('%H:%M')}:\n{medication_lines}"
            )

        return {
            "type": "due",
            "medication_id": first["medication_id"],
            "medication_ids": medication_ids,
            "notify_service": first["notify_service"],
            "scheduled_time": scheduled_time,
            "message": message,
            "actions": [
                {
                    "action": f"MEDICATION_CONFIRMED_{item['medication_id']}",
                    "title": f"Taken: {item['medication_name']}",
                }
                for item in sorted_due_medications
            ],
            "notification_suffix": "_".join(medication_ids) if len(medication_ids) > 1 else None,
        }

    def _build_missed_alert(self, missed_medications: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a single missed-dose alert for one medication or a grouped set."""
        sorted_missed_medications = sorted(
            missed_medications,
            key=lambda item: (item["scheduled_time"], item["medication_name"].lower(), item["medication_id"]),
        )
        first = sorted_missed_medications[0]
        medication_ids = [item["medication_id"] for item in sorted_missed_medications]
        scheduled_time = first["scheduled_time"]

        if len(sorted_missed_medications) == 1:
            message = (
                f"{first['profile_name']} missed the scheduled {first['medication_name']} "
                f"dose from {scheduled_time.strftime('%H:%M')}."
            )
        else:
            medication_lines = "\n".join(
                f"- {item['medication_name']} ({item['dosage']})"
                for item in sorted_missed_medications
            )
            message = (
                f"{first['profile_name']} missed {len(sorted_missed_medications)} scheduled medications "
                f"from {scheduled_time.strftime('%H:%M')}:\n{medication_lines}"
            )

        return {
            "type": "missed",
            "medication_id": first["medication_id"],
            "medication_ids": medication_ids,
            "notify_service": first["notify_service"],
            "scheduled_time": scheduled_time,
            "message": message,
            "actions": [
                {
                    "action": f"MEDICATION_CONFIRMED_{item['medication_id']}",
                    "title": f"Mark Taken: {item['medication_name']}",
                }
                for item in sorted_missed_medications
            ],
            "notification_suffix": "_".join(medication_ids) if len(medication_ids) > 1 else None,
        }

    def _effective_due_start(self, medication: Medication, scheduled_time: datetime) -> datetime:
        """Return the effective due start, including any active snooze."""
        snoozed_until = self._active_snoozed_until(medication, dt_util.now())
        if not snoozed_until:
            return scheduled_time
        if snoozed_until <= scheduled_time:
            return scheduled_time
        if snoozed_until.date() != scheduled_time.date():
            return scheduled_time
        return snoozed_until

    def _active_snoozed_until(self, medication: Medication, now: datetime) -> datetime | None:
        """Return the active snooze time when it is still in the future."""
        if not medication.snoozed_until:
            return None
        snoozed_until = datetime.fromisoformat(medication.snoozed_until)
        if snoozed_until <= now:
            return None
        return snoozed_until

    def _validate_duplicate_guard(self, medication: Medication, timestamp: datetime) -> None:
        """Prevent accidental duplicate logs inside the guard window."""
        if medication.duplicate_guard_minutes <= 0 or not medication.dose_logs:
            return
        last_taken = medication.dose_logs[-1].taken_at
        if _is_naive_datetime(last_taken):
            return
        if timestamp <= last_taken:
            return
        if timestamp < last_taken + timedelta(minutes=medication.duplicate_guard_minutes):
            remaining = int((last_taken + timedelta(minutes=medication.duplicate_guard_minutes) - timestamp).total_seconds() // 60)
            raise HomeAssistantError(
                f"Duplicate-dose protection blocked this log for {medication.name}. "
                f"Try again in about {max(remaining, 1)} minutes or override the duplicate check."
            )

    def _duplicate_dose_warning(self, medication: Medication, now: datetime) -> str | None:
        """Return a warning when a new dose may be too soon."""
        if medication.duplicate_guard_minutes <= 0 or not medication.dose_logs:
            return None
        latest_allowed = medication.dose_logs[-1].taken_at + timedelta(minutes=medication.duplicate_guard_minutes)
        if latest_allowed <= now:
            return None
        return f"Duplicate-dose protection active until {latest_allowed.strftime('%H:%M')}."

    def _stock_depletion_date(self, medication: Medication, now: datetime) -> datetime | None:
        """Estimate when stock will run out based on current quantity and schedule."""
        if medication.quantity is None:
            return None
        daily_doses = len(medication.schedules)
        if daily_doses <= 0:
            return None
        days_remaining = medication.quantity / daily_doses
        return now + timedelta(days=days_remaining)

    def _stock_status(
        self,
        medication: Medication,
        now: datetime,
        depletion_date: datetime | None,
    ) -> str:
        """Return a friendly stock forecast status."""
        if medication.quantity is None:
            return "Not tracked"
        if self._needs_refill(medication):
            return "Refill needed"
        if depletion_date is None:
            return "Unknown"
        days_left = (depletion_date - now).total_seconds() / 86400
        if days_left <= 3:
            return "Running low"
        if days_left <= 7:
            return "Refill soon"
        return "Stock OK"

    def _build_refill_alert(self, refill_medications: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a single refill alert for one medication or a grouped set."""
        sorted_refill_medications = sorted(
            refill_medications,
            key=lambda item: (item["medication_name"].lower(), item["medication_id"]),
        )
        first = sorted_refill_medications[0]
        medication_ids = [item["medication_id"] for item in sorted_refill_medications]

        if len(sorted_refill_medications) == 1:
            message = (
                f"{first['medication_name']} is running low for {first['profile_name']} "
                f"with {first['remaining']:g} doses remaining."
            )
        else:
            medication_lines = "\n".join(
                f"- {item['medication_name']} ({item['dosage']}): {item['remaining']:g} doses remaining"
                for item in sorted_refill_medications
            )
            message = (
                f"{first['profile_name']} has {len(sorted_refill_medications)} medications running low:\n"
                f"{medication_lines}"
            )

        return {
            "type": "refill",
            "medication_id": first["medication_id"],
            "medication_ids": medication_ids,
            "notify_service": first["notify_service"],
            "scheduled_time": None,
            "message": message,
            "notification_suffix": "_".join(medication_ids) if len(medication_ids) > 1 else None,
        }

    def _build_caregiver_alert(self, caregiver_medications: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a single caregiver confirmation alert for one medication or a grouped set."""
        sorted_caregiver_medications = sorted(
            caregiver_medications,
            key=lambda item: (item["scheduled_time"], item["medication_name"].lower(), item["medication_id"]),
        )
        first = sorted_caregiver_medications[0]
        medication_ids = [item["medication_id"] for item in sorted_caregiver_medications]
        scheduled_time = first["scheduled_time"]
        caregiver_name = first["caregiver_name"]

        if len(sorted_caregiver_medications) == 1:
            message = (
                f"{caregiver_name} should confirm the latest logged dose of "
                f"{first['medication_name']} for {first['profile_name']}."
            )
        else:
            medication_lines = "\n".join(
                f"- {item['medication_name']} ({item['dosage']})"
                for item in sorted_caregiver_medications
            )
            message = (
                f"{caregiver_name} should confirm {len(sorted_caregiver_medications)} logged medications "
                f"for {first['profile_name']} from {scheduled_time.strftime('%H:%M')}:\n{medication_lines}"
            )

        return {
            "type": "caregiver_confirmation",
            "medication_id": first["medication_id"],
            "medication_ids": medication_ids,
            "notify_service": first["notify_service"],
            "scheduled_time": scheduled_time,
            "message": message,
            "notification_suffix": "_".join(medication_ids) if len(medication_ids) > 1 else None,
        }


def _is_naive_datetime(value: datetime) -> bool:
    """Return whether a datetime has no usable timezone info."""
    return value.tzinfo is None or value.tzinfo.utcoffset(value) is None
