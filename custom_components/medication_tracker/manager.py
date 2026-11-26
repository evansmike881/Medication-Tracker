"""Medication business logic."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
import logging
import math
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    ACTION_ALL_PREFIX,
    ACTION_CONFIRMED_PREFIX,
    ACTION_GROUP_PREFIX,
    ACTION_GROUP_SNOOZE_PREFIX,
    ACTION_SKIP_PREFIX,
    ACTION_SNOOZE_ALL_PREFIX,
    ACTION_SNOOZE_PREFIX,
    DEFAULT_MAX_REPEATS,
    DEFAULT_MISSED_AFTER_MINUTES,
    DEFAULT_REMINDER_MINUTES,
    DEFAULT_REPEAT_EVERY_MINUTES,
    DEFAULT_SETTINGS,
    EARLY_WINDOW_MINUTES,
    HISTORY_WINDOW_DAYS,
    LOG_RETENTION_DAYS,
    MAX_INTERVAL_DAYS,
    SETTING_ALL_TAG_IDS,
    SETTING_ANNOUNCE_HOME_ENTITY,
    SETTING_ANNOUNCE_SERVICE,
    SETTING_CRITICAL,
    SETTING_DEFAULT_NOTIFY,
    SETTING_ESCALATION_NOTIFY,
    SETTING_FALLBACK_NOTIFY,
    SETTING_PROFILE_TAGS,
    SETTING_QUIET_END,
    SETTING_QUIET_START,
    BACKUP_DIR,
    BACKUP_FORMAT,
    BACKUP_KEEP,
    FOOD_NOTES,
    SETTING_LAST_WEEKLY,
    SETTING_PAUSES,
    SETTING_PROFILE_NOTIFY,
    SETTING_WEEKLY_DAY,
    SETTING_WEEKLY_SERVICE,
    VERSION,
)
from .medication_database import MedicationDatabase
from .models import DoseLog, Group, Medication
from .store import MedicationTrackerStore

_LOGGER = logging.getLogger(__name__)

# How long after a scheduled time a "take all" or tag scan still counts as that dose.
LATE_WINDOW = timedelta(hours=12)

STATUS_TAKEN = "Taken"
STATUS_SKIPPED = "Skipped"
STATUS_MISSED = "Missed Dose"
STATUS_SNOOZED = "Snoozed"
STATUS_DUE = "Due Now"
STATUS_ON_TRACK = "On Track"


class _MatchState:
    """Scheduled occurrences, their dose windows and which ones have a dose."""

    __slots__ = ("occurrences", "window_starts", "matched")

    def __init__(
        self,
        occurrences: list[datetime],
        window_starts: list[datetime],
        matched: set[datetime],
    ) -> None:
        self.occurrences = occurrences
        self.window_starts = window_starts
        self.matched = matched


class MedicationTrackerManager:
    """Manage medication records and dose calculations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.store = MedicationTrackerStore(hass)
        self.database = MedicationDatabase()
        self.medications: dict[str, Medication] = {}
        self.settings: dict[str, Any] = deepcopy(DEFAULT_SETTINGS)
        self.groups: dict[str, Group] = {}

    async def async_initialize(self) -> None:
        """Load persisted state."""
        self.database = await MedicationDatabase.async_load(self.hass)
        self.medications, self.settings, self.groups = await self.store.async_load_all()
        self._prune_old_logs()
        self._sync_groups()

    def _prune_old_logs(self) -> None:
        """Drop dose logs older than the retention period so storage stays small."""
        cutoff = dt_util.now() - timedelta(days=LOG_RETENTION_DAYS)
        for medication in self.medications.values():
            kept = [item for item in medication.dose_logs if dt_util.as_local(item.taken_at) >= cutoff]
            if len(kept) != len(medication.dose_logs):
                medication.dose_logs = kept

    # ------------------------------------------------------------------
    # Medication CRUD
    # ------------------------------------------------------------------

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
        repeat_every_minutes: int | None = None,
        max_repeats: int | None = None,
        days_of_week: list[int] | None = None,
        end_date: str | None = None,
        as_needed: bool | None = None,
        max_doses_per_day: int | None = None,
        interval_days: int | None = None,
        anchor_date: str | None = None,
        escalate_after_minutes: int | None = None,
        group_id: str | None = None,
        food_note: str | None = None,
        keep_apart: list[str] | None = None,
        keep_apart_minutes: int | None = None,
    ) -> Medication:
        """Create or update a medication."""
        existing = self.medications.get(medication_id)
        if as_needed is None:
            as_needed = existing.as_needed if existing else False
        # None keeps the current group, "" removes it. As-needed medication is never grouped.
        if group_id is None:
            group_value = existing.group_id if existing else None
        else:
            group_value = group_id or None
        if as_needed:
            group_value = None
        group = self.groups.get(group_value) if group_value else None
        if group_value and group is None:
            raise HomeAssistantError(f"Unknown group: {group_value}")
        if group is not None and group.profile_id != profile_id:
            raise HomeAssistantError(f"The group '{group.name}' belongs to {group.profile_name}.")
        normalized_schedules = self._normalize_schedules(schedules or [], allow_empty=bool(as_needed) or group is not None)
        normalized_days = self._normalize_days(days_of_week)
        # For these, None keeps the stored value and "" / 0 clears it.
        if end_date is None:
            end_value = existing.end_date if existing else None
        else:
            end_value = self._parse_date(end_date, "end_date")
        if interval_days is None:
            interval_value = existing.interval_days if existing else 1
        else:
            interval_value = int(interval_days)
        if interval_value < 1 or interval_value > MAX_INTERVAL_DAYS:
            raise HomeAssistantError(f"interval_days must be between 1 and {MAX_INTERVAL_DAYS}.")
        if anchor_date:
            anchor_value = self._parse_date(anchor_date, "anchor_date")
        else:
            anchor_value = (existing.anchor_date if existing else None) or dt_util.now().date()
        if max_doses_per_day is None:
            max_doses_value = existing.max_doses_per_day if existing else None
        else:
            max_doses_value = int(max_doses_per_day) or None
        if escalate_after_minutes is None:
            escalate_value = existing.escalate_after_minutes if existing else 0
        else:
            escalate_value = max(int(escalate_after_minutes), 0)
        if food_note is None:
            food_value = existing.food_note if existing else ""
        else:
            food_value = food_note or ""
            if food_value and food_value not in FOOD_NOTES:
                raise HomeAssistantError(f"food_note must be one of: {', '.join(FOOD_NOTES)}.")
        if keep_apart is None:
            apart_value = list(existing.keep_apart) if existing else []
        else:
            apart_value = [m for m in dict.fromkeys(keep_apart) if m != medication_id]
            unknown = [m for m in apart_value if m not in self.medications]
            if unknown:
                raise HomeAssistantError(f"Unknown medication to keep apart from: {unknown[0]}")
        if keep_apart_minutes is None:
            apart_minutes = existing.keep_apart_minutes if existing else 120
        else:
            apart_minutes = max(15, min(int(keep_apart_minutes or 120), 720))
        database_entry = self.database.get(database_entry_id) if database_entry_id else None
        computed_purpose = purpose or (database_entry.get("purpose", "") if database_entry else "")
        computed_form = form or (database_entry.get("form", "") if database_entry else "")
        computed_instructions = instructions or (database_entry.get("instructions", "") if database_entry else "")
        computed_strength_options = (
            list(strength_options)
            if strength_options is not None
            else list(database_entry.get("strength_options", [])) if database_entry else []
        )
        if repeat_every_minutes is None:
            repeat_every_minutes = existing.repeat_every_minutes if existing else DEFAULT_REPEAT_EVERY_MINUTES
        if max_repeats is None:
            max_repeats = existing.max_repeats if existing else DEFAULT_MAX_REPEATS
        # None keeps the stored value, an empty string clears it.
        if caregiver_name is None:
            caregiver_name = existing.caregiver_name if existing else None
        if caregiver_notify_service is None:
            caregiver_notify_service = existing.caregiver_notify_service if existing else None
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
            caregiver_name=caregiver_name or None,
            caregiver_notify_service=caregiver_notify_service or None,
            confirmation_required=confirmation_required,
            reminder_minutes=reminder_minutes,
            missed_after_minutes=missed_after_minutes,
            duplicate_guard_minutes=duplicate_guard_minutes,
            repeat_every_minutes=max(int(repeat_every_minutes), 0),
            max_repeats=max(int(max_repeats), 0),
            days_of_week=normalized_days,
            end_date=end_value,
            as_needed=bool(as_needed),
            max_doses_per_day=max_doses_value,
            interval_days=interval_value,
            anchor_date=anchor_value,
            escalate_after_minutes=escalate_value,
            last_escalation_notification=existing.last_escalation_notification if existing else None,
            group_id=group_value,
            food_note=food_value,
            keep_apart=apart_value,
            keep_apart_minutes=apart_minutes,
            sort_order=(
                existing.sort_order
                if existing and existing.group_id == group_value
                else self._next_sort_order(profile_id, group_value)
            ),
            created_at=existing.created_at if existing else dt_util.now().isoformat(),
            last_due_sent_at=existing.last_due_sent_at if existing else None,
            due_repeat_count=existing.due_repeat_count if existing else 0,
            last_due_notification=existing.last_due_notification if existing else None,
            last_missed_notification=existing.last_missed_notification if existing else None,
            last_refill_notification=existing.last_refill_notification if existing else None,
            last_caregiver_notification=existing.last_caregiver_notification if existing else None,
            snoozed_until=existing.snoozed_until if existing else None,
            skipped_occurrences=list(existing.skipped_occurrences) if existing else [],
            start_date=existing.start_date if existing else dt_util.now().date(),
            dose_logs=list(existing.dose_logs) if existing else [],
        )
        if group is not None:
            self._apply_group_to_medication(group, medication)
        self.medications[medication_id] = medication
        await self._async_save()
        return medication

    async def async_remove_medication(self, medication_id: str) -> None:
        """Remove a medication."""
        self._get_medication(medication_id)
        self.medications.pop(medication_id)
        await self._async_save()

    async def async_reset_history(self, medication_id: str) -> Medication:
        """Start the medication's history fresh, e.g. after a long break."""
        medication = self._get_medication(medication_id)
        now = dt_util.now()
        medication.start_date = now.date()
        medication.created_at = now.isoformat()
        medication.skipped_occurrences = []
        medication.last_due_notification = None
        medication.last_missed_notification = None
        medication.last_caregiver_notification = None
        medication.last_due_sent_at = None
        medication.last_escalation_notification = None
        medication.due_repeat_count = 0
        medication.snoozed_until = None
        await self._async_save()
        return medication

    async def async_refill_medication(self, medication_id: str, quantity: float) -> Medication:
        """Add remaining quantity."""
        medication = self._get_medication(medication_id)
        current_quantity = medication.quantity or 0
        medication.quantity = current_quantity + quantity
        medication.last_refill_notification = None
        await self._async_save()
        return medication

    # ------------------------------------------------------------------
    # Doses
    # ------------------------------------------------------------------

    def _apply_dose(
        self,
        medication: Medication,
        timestamp: datetime,
        source: str,
        confirmed_by: str | None,
        allow_duplicate: bool,
        taken_by: str | None = None,
    ) -> None:
        """Record a dose in memory without saving."""
        if _is_naive_datetime(timestamp):
            timestamp = dt_util.as_local(dt_util.as_utc(timestamp))
        if not allow_duplicate:
            self._validate_duplicate_guard(medication, timestamp)
            if medication.as_needed and medication.max_doses_per_day:
                day = dt_util.as_local(timestamp).date()
                taken_that_day = sum(
                    1 for item in medication.dose_logs if dt_util.as_local(item.taken_at).date() == day
                )
                if taken_that_day >= medication.max_doses_per_day:
                    raise HomeAssistantError(
                        f"{medication.name}: the limit of {medication.max_doses_per_day} doses "
                        "per day has been reached."
                    )
        medication.dose_logs.append(
            DoseLog(taken_at=timestamp, source=source, confirmed_by=confirmed_by, taken_by=taken_by)
        )
        medication.dose_logs.sort(key=lambda item: item.taken_at)

        if medication.quantity is not None:
            medication.quantity = max(medication.quantity - 1, 0)

        medication.last_due_notification = None
        medication.last_missed_notification = None
        medication.last_caregiver_notification = None
        medication.last_due_sent_at = None
        medication.due_repeat_count = 0
        medication.snoozed_until = None

    async def async_log_dose(
        self,
        medication_id: str,
        taken_at: datetime | None = None,
        source: str = "manual",
        confirmed_by: str | None = None,
        allow_duplicate: bool = False,
        taken_by: str | None = None,
    ) -> Medication:
        """Log a dose for a medication."""
        medication = self._get_medication(medication_id)
        timestamp = taken_at or dt_util.now()
        self._apply_dose(medication, timestamp, source, confirmed_by, allow_duplicate, taken_by)
        await self._async_save()
        return medication

    async def async_log_outstanding(
        self,
        *,
        profile_id: str | None = None,
        medication_ids: Iterable[str] | None = None,
        group_id: str | None = None,
        source: str = "manual",
        confirmed_by: str | None = None,
        taken_by: str | None = None,
    ) -> dict[str, list[str]]:
        """Log one dose for every medication that is currently due or overdue.

        Returns the ids that were logged and the ids a duplicate-dose guard blocked.
        """
        now = dt_util.now()
        wanted = set(medication_ids) if medication_ids is not None else None
        logged: list[str] = []
        blocked: list[str] = []
        for medication in list(self.medications.values()):
            if profile_id and medication.profile_id != profile_id:
                continue
            if group_id and medication.group_id != group_id:
                continue
            if wanted is not None and medication.medication_id not in wanted:
                continue
            if self._outstanding_occurrence(medication, now) is None:
                continue
            try:
                self._apply_dose(medication, now, source, confirmed_by, False, taken_by)
            except HomeAssistantError:
                blocked.append(medication.medication_id)
                continue
            logged.append(medication.medication_id)
        if logged:
            await self._async_save()
        return {"logged": logged, "blocked": blocked}

    async def async_delete_dose(self, medication_id: str, taken_at: str) -> Medication:
        """Delete a logged dose (for example one logged by mistake)."""
        medication = self._get_medication(medication_id)
        target = datetime.fromisoformat(taken_at)
        for index, dose_log in enumerate(medication.dose_logs):
            if dose_log.taken_at == target or dose_log.taken_at.isoformat() == taken_at:
                medication.dose_logs.pop(index)
                if medication.quantity is not None:
                    medication.quantity += 1
                medication.last_due_notification = None
                medication.last_missed_notification = None
                medication.last_caregiver_notification = None
                await self._async_save()
                return medication
        raise HomeAssistantError("That dose log entry was not found.")

    async def async_undo_last(self, medication_id: str) -> Medication:
        """Remove the most recent logged dose."""
        medication = self._get_medication(medication_id)
        if not medication.dose_logs:
            raise HomeAssistantError("There is no logged dose to undo.")
        return await self.async_delete_dose(medication_id, medication.dose_logs[-1].taken_at.isoformat())

    async def async_snooze_medication(self, medication_id: str, minutes: int) -> Medication:
        """Snooze a medication reminder for a number of minutes."""
        medication = self._get_medication(medication_id)
        medication.snoozed_until = (dt_util.now() + timedelta(minutes=minutes)).isoformat()
        medication.last_due_notification = None
        medication.last_due_sent_at = None
        medication.due_repeat_count = 0
        await self._async_save()
        return medication

    async def async_skip_medication_occurrence(
        self,
        medication_id: str,
        scheduled_time: datetime | None = None,
    ) -> Medication:
        """Skip the next or supplied scheduled occurrence for a medication."""
        medication = self._get_medication(medication_id)
        now = dt_util.now()
        occurrence = (
            scheduled_time
            or self._outstanding_occurrence(medication, now)
            or self._current_due_schedule(medication, now)
            or self._next_scheduled_dose(medication, now)
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

    # ------------------------------------------------------------------
    # Settings and lookups
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def profile_id_for(self, profile_name: str) -> str:
        """Reuse the id of an existing person with this name, or make a new one."""
        for profile_id, name in self.list_profiles().items():
            if name.casefold() == profile_name.strip().casefold():
                return profile_id
        for group in self.groups.values():
            if group.profile_name.casefold() == profile_name.strip().casefold():
                return group.profile_id
        return slugify(profile_name) or "person"

    def unique_medication_id(self, profile_name: str, name: str) -> str:
        """Return an unused medication id for a person and medication name."""
        base = slugify(f"{profile_name}_{name}") or "medication"
        candidate, counter = base, 2
        while candidate in self.medications:
            candidate = f"{base}_{counter}"
            counter += 1
        return candidate

    def _group_name(self, medication: Medication) -> str | None:
        group = self.groups.get(medication.group_id) if medication.group_id else None
        return group.name if group else None

    def _item_group(self, medication: Medication) -> dict[str, Any]:
        return {"group_id": medication.group_id, "group_name": self._group_name(medication)}

    def _member_key(self, medication: Medication) -> tuple[int, str]:
        return (medication.sort_order, medication.name.lower())

    def group_members(self, group_id: str | None, profile_id: str | None = None) -> list[Medication]:
        """Medications in a group (or the ungrouped ones for a person), in display order."""
        members = [
            medication
            for medication in self.medications.values()
            if medication.group_id == group_id and (profile_id is None or medication.profile_id == profile_id)
        ]
        return sorted(members, key=self._member_key)

    def _next_sort_order(self, profile_id: str, group_id: str | None) -> int:
        members = self.group_members(group_id, profile_id)
        return (max(member.sort_order for member in members) + 1) if members else 0

    def _apply_group_to_medication(self, group: Group, medication: Medication) -> None:
        """Copy the group's schedule onto a member so all per-medication logic keeps working."""
        medication.schedules = list(group.schedules)
        medication.days_of_week = list(group.days_of_week) if group.days_of_week else None
        medication.interval_days = group.interval_days
        medication.anchor_date = group.anchor_date or medication.anchor_date
        medication.notification_enabled = group.notification_enabled
        if group.notify_service:
            medication.notify_service = group.notify_service

    def _sync_groups(self) -> None:
        """Make every member match its group (also drops references to deleted groups)."""
        for medication in self.medications.values():
            if not medication.group_id:
                continue
            group = self.groups.get(medication.group_id)
            if group is None:
                medication.group_id = None
            else:
                self._apply_group_to_medication(group, medication)

    async def async_save_group(
        self,
        *,
        group_id: str | None = None,
        profile_id: str,
        profile_name: str,
        name: str,
        schedules: list[str],
        days_of_week: list[int] | None = None,
        interval_days: int = 1,
        anchor_date: str | None = None,
        notify_service: str | None = None,
        nfc_tag_id: str | None = None,
        notification_enabled: bool = True,
        member_ids: list[str] | None = None,
    ) -> Group:
        """Create or update a group, optionally replacing its member list."""
        name = (name or "").strip()
        if not name:
            raise HomeAssistantError("A group needs a name.")
        interval = int(interval_days or 1)
        if interval < 1 or interval > MAX_INTERVAL_DAYS:
            raise HomeAssistantError(f"interval_days must be between 1 and {MAX_INTERVAL_DAYS}.")
        existing = self.groups.get(group_id) if group_id else None
        if group_id and existing is None:
            raise HomeAssistantError(f"Unknown group: {group_id}")
        if existing and existing.profile_id != profile_id:
            raise HomeAssistantError("A group cannot be moved to another person.")
        if not existing:
            base = slugify(f"{profile_name}_{name}") or "group"
            group_id, counter = base, 2
            while group_id in self.groups:
                group_id = f"{base}_{counter}"
                counter += 1
        group = Group(
            group_id=group_id,
            profile_id=profile_id,
            profile_name=profile_name,
            name=name,
            schedules=self._normalize_schedules(schedules or []),
            days_of_week=self._normalize_days(days_of_week),
            interval_days=interval,
            anchor_date=(self._parse_date(anchor_date, "anchor_date") if anchor_date else None)
            or (existing.anchor_date if existing else None)
            or dt_util.now().date(),
            notify_service=notify_service or None,
            nfc_tag_id=nfc_tag_id or None,
            notification_enabled=bool(notification_enabled),
            order=existing.order if existing else self._next_group_order(profile_id),
        )
        if member_ids is not None:
            for medication_id in member_ids:
                medication = self._get_medication(medication_id)
                if medication.profile_id != profile_id:
                    raise HomeAssistantError(f"{medication.name} belongs to {medication.profile_name}.")
                if medication.as_needed:
                    raise HomeAssistantError(f"{medication.name} is as-needed, so it can't be in a timed group.")
        self.groups[group_id] = group
        if member_ids is not None:
            wanted = list(dict.fromkeys(member_ids))
            for medication in self.medications.values():
                if medication.group_id == group_id and medication.medication_id not in wanted:
                    medication.group_id = None
            for position, medication_id in enumerate(wanted):
                medication = self.medications[medication_id]
                medication.group_id = group_id
                medication.sort_order = position
        for medication in self.group_members(group_id):
            self._apply_group_to_medication(group, medication)
        await self._async_save()
        return group

    def _next_group_order(self, profile_id: str) -> int:
        orders = [group.order for group in self.groups.values() if group.profile_id == profile_id]
        return (max(orders) + 1) if orders else 0

    async def async_delete_group(self, group_id: str) -> None:
        """Delete a group. Its medications stay (ungrouped, keeping their schedule)."""
        if group_id not in self.groups:
            raise HomeAssistantError(f"Unknown group: {group_id}")
        profile_id = self.groups[group_id].profile_id
        self.groups.pop(group_id)
        for position, medication in enumerate(self.group_members(group_id)):
            medication.group_id = None
            medication.sort_order = self._next_sort_order(profile_id, None) + position
        await self._async_save()

    async def async_move_medication(
        self,
        medication_id: str,
        group_id: str | None,
        index: int | None = None,
    ) -> Medication:
        """Move a medication into a group (or out of all groups) at a position."""
        medication = self._get_medication(medication_id)
        group = self.groups.get(group_id) if group_id else None
        if group_id and group is None:
            raise HomeAssistantError(f"Unknown group: {group_id}")
        if group is not None:
            if group.profile_id != medication.profile_id:
                raise HomeAssistantError(f"The group '{group.name}' belongs to {group.profile_name}.")
            if medication.as_needed:
                raise HomeAssistantError(f"{medication.name} is as-needed, so it can't be in a timed group.")
        source_group = medication.group_id
        medication.group_id = group_id or None
        if group is not None:
            self._apply_group_to_medication(group, medication)
        siblings = [
            member
            for member in self.group_members(group_id or None, medication.profile_id)
            if member.medication_id != medication_id
        ]
        position = len(siblings) if index is None else max(0, min(int(index), len(siblings)))
        siblings.insert(position, medication)
        for order, member in enumerate(siblings):
            member.sort_order = order
        if source_group != (group_id or None):
            for order, member in enumerate(self.group_members(source_group, medication.profile_id)):
                member.sort_order = order
        await self._async_save()
        return medication

    async def async_reorder_groups(self, profile_id: str, group_ids: list[str]) -> None:
        """Set the display order of a person's groups."""
        for group_id in group_ids:
            group = self.groups.get(group_id)
            if group is None or group.profile_id != profile_id:
                raise HomeAssistantError(f"Unknown group for this person: {group_id}")
        rest = sorted(
            (g for g in self.groups.values() if g.profile_id == profile_id and g.group_id not in group_ids),
            key=lambda g: g.order,
        )
        for position, group_id in enumerate([*group_ids, *[g.group_id for g in rest]]):
            self.groups[group_id].order = position
        await self._async_save()

    async def async_quick_add(
        self,
        *,
        profile_name: str,
        items: list[dict[str, Any]],
        group_id: str | None = None,
        new_group: dict[str, Any] | None = None,
        schedules: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add many medications at once, optionally into a (new) group."""
        profile_name = profile_name.strip()
        if not profile_name:
            raise HomeAssistantError("Who are these medications for?")
        names = [item for item in items if str(item.get("name", "")).strip()]
        if not names:
            raise HomeAssistantError("Add at least one medication.")
        profile_id = self.profile_id_for(profile_name)
        if new_group:
            group = await self.async_save_group(
                profile_id=profile_id,
                profile_name=profile_name,
                name=new_group.get("name", ""),
                schedules=new_group.get("schedules") or schedules or [],
                days_of_week=new_group.get("days_of_week"),
                notify_service=new_group.get("notify_service"),
            )
            group_id = group.group_id
        elif not group_id and not schedules:
            raise HomeAssistantError("Choose a group or at least one time.")
        created: list[str] = []
        for item in names:
            medication_id = self.unique_medication_id(profile_name, str(item["name"]))
            await self.async_add_medication(
                profile_id=profile_id,
                profile_name=profile_name,
                medication_id=medication_id,
                medication_name=str(item["name"]).strip(),
                dosage=str(item.get("dosage") or "1 dose").strip(),
                schedules=[] if group_id else list(schedules or []),
                group_id=group_id or "",
            )
            created.append(medication_id)
        return {"created": created, "group_id": group_id}

    def get_groups_view(self) -> list[dict[str, Any]]:
        """Return groups with their ordered members, for the panel."""
        rows = []
        for group in sorted(self.groups.values(), key=lambda g: (g.profile_name.lower(), g.order, g.name.lower())):
            rows.append(
                {
                    **group.as_dict(),
                    "anchor_date": group.anchor_date.isoformat() if group.anchor_date else None,
                    "member_ids": [m.medication_id for m in self.group_members(group.group_id)],
                }
            )
        return rows

    def outstanding_ids(self, profile_id: str | None = None, group_id: str | None = None) -> list[str]:
        """Medications that currently have a dose waiting, optionally filtered."""
        now = dt_util.now()
        return [
            medication.medication_id
            for medication in self.medications.values()
            if (not profile_id or medication.profile_id == profile_id)
            and (not group_id or medication.group_id == group_id)
            and self._outstanding_occurrence(medication, now) is not None
        ]

    async def async_update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Validate and store integration-wide settings."""
        for key, value in updates.items():
            if key not in DEFAULT_SETTINGS:
                raise HomeAssistantError(f"Unknown setting: {key}")
            if key in (SETTING_DEFAULT_NOTIFY, SETTING_FALLBACK_NOTIFY):
                self.settings[key] = value or None
            elif key == SETTING_ALL_TAG_IDS:
                self.settings[key] = sorted({str(tag).strip() for tag in (value or []) if str(tag).strip()})
            elif key == SETTING_CRITICAL:
                self.settings[key] = bool(value)
            elif key in (SETTING_ESCALATION_NOTIFY, SETTING_ANNOUNCE_SERVICE, SETTING_ANNOUNCE_HOME_ENTITY):
                self.settings[key] = value or None
            elif key in (SETTING_QUIET_START, SETTING_QUIET_END):
                if value:
                    try:
                        value = time.fromisoformat(value).strftime("%H:%M")
                    except ValueError as err:
                        raise HomeAssistantError(f"{key} must be HH:MM.") from err
                self.settings[key] = value or None
            elif key == SETTING_PROFILE_NOTIFY:
                self.settings[key] = {
                    str(profile): str(service).strip()
                    for profile, service in (value or {}).items()
                    if profile and str(service or "").strip()
                }
            elif key == SETTING_WEEKLY_SERVICE:
                self.settings[key] = value or None
            elif key == SETTING_WEEKLY_DAY:
                day = int(value if value is not None else 6)
                if day < 0 or day > 6:
                    raise HomeAssistantError("weekly_summary_day must be 0 (Monday) to 6 (Sunday).")
                self.settings[key] = day
            elif key == SETTING_PROFILE_TAGS:
                self.settings[key] = {
                    str(tag).strip(): str(profile)
                    for tag, profile in (value or {}).items()
                    if str(tag).strip() and profile
                }
        await self._async_save()
        return self.settings

    def resolve_notify_service(self, medication: Medication, caregiver: bool = False) -> str | None:
        """Return the notify service to use for a medication."""
        if caregiver and medication.caregiver_notify_service:
            return medication.caregiver_notify_service
        return (
            medication.notify_service
            or self.settings.get(SETTING_PROFILE_NOTIFY, {}).get(medication.profile_id)
            or self.settings.get(SETTING_DEFAULT_NOTIFY)
        )

    def list_medications(self) -> Iterable[Medication]:
        """Return all medications."""
        return self.medications.values()

    def list_profiles(self) -> dict[str, str]:
        """Return profile names keyed by profile id."""
        profiles = {medication.profile_id: medication.profile_name for medication in self.medications.values()}
        return dict(sorted(profiles.items(), key=lambda item: item[1].lower()))

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

    def resolve_tag(self, tag_id: str) -> tuple[str, Any] | None:
        """Work out what a scanned NFC tag should do.

        Returns ("medication", Medication), ("profile", profile_id), ("all", None) or None.
        """
        medication = self.get_by_tag(tag_id)
        if medication is not None:
            return "medication", medication
        for group in self.groups.values():
            if group.nfc_tag_id and group.nfc_tag_id == tag_id:
                return "group", group
        profile_id = self.settings.get(SETTING_PROFILE_TAGS, {}).get(tag_id)
        if profile_id:
            return "profile", profile_id
        if tag_id in self.settings.get(SETTING_ALL_TAG_IDS, []):
            return "all", None
        return None

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def get_snapshot(self, medication_id: str) -> dict[str, Any]:
        """Return a computed status snapshot."""
        medication = self._get_medication(medication_id)
        now = dt_util.now()
        today = now.date()
        state = self._match_state(medication, now)
        schedule_occurrences = [
            occurrence
            for occurrence in state.occurrences
            if occurrence.date() <= today and occurrence.isoformat() not in medication.skipped_occurrences
        ]
        matched_occurrences = [occurrence for occurrence in schedule_occurrences if occurrence in state.matched]
        past_due_today = [
            scheduled
            for scheduled in schedule_occurrences
            if scheduled.date() == today and scheduled <= now
        ]
        taken_today = [
            scheduled
            for scheduled in matched_occurrences
            if scheduled.date() == today
        ]
        last_dose = medication.dose_logs[-1].taken_at if medication.dose_logs else None
        last_confirmed_by = medication.dose_logs[-1].confirmed_by if medication.dose_logs else None
        next_dose = self._next_scheduled_dose(medication, now)
        missed_doses = self._missed_doses(medication, now, state)
        recent_missed = self._recent_missed(medication, now, state)
        total_scheduled = len(
            [occurrence for occurrence in schedule_occurrences if self._past_missed_threshold(medication, occurrence, now)]
            + [occurrence for occurrence in matched_occurrences if not self._past_missed_threshold(medication, occurrence, now)]
        )
        compliance = round((len(matched_occurrences) / total_scheduled) * 100, 1) if total_scheduled else 100.0
        compliance = min(compliance, 100.0)
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
        outstanding = self._outstanding_occurrence(medication, now, state)

        return {
            "medication_id": medication.medication_id,
            "profile_id": medication.profile_id,
            "profile_name": medication.profile_name,
            "belongs_to": medication.profile_name,
            "group_id": medication.group_id,
            "group_name": self._group_name(medication),
            "sort_order": medication.sort_order,
            "medication_name": medication.name,
            "dosage": medication.dosage,
            "notes": medication.notes,
            "instructions": medication.instructions,
            "purpose": medication.purpose,
            "form": medication.form,
            "strength_options": medication.strength_options,
            "schedules": medication.schedules,
            "days_of_week": medication.days_of_week,
            "interval_days": medication.interval_days,
            "anchor_date": medication.anchor_date.isoformat() if medication.anchor_date else None,
            "end_date": medication.end_date.isoformat() if medication.end_date else None,
            "course_ended": bool(medication.end_date and today > medication.end_date),
            "as_needed": medication.as_needed,
            "max_doses_per_day": medication.max_doses_per_day,
            "doses_today": sum(
                1 for item in medication.dose_logs if dt_util.as_local(item.taken_at).date() == today
            ),
            "escalate_after_minutes": medication.escalate_after_minutes,
            "last_taken_by": medication.dose_logs[-1].taken_by if medication.dose_logs else None,
            "dose_count": len(medication.dose_logs),
            "last_taken": last_dose.isoformat() if last_dose else None,
            "last_confirmed_by": last_confirmed_by,
            "next_dose": next_dose.isoformat() if next_dose else None,
            "missed_doses": missed_doses,
            "recent_missed": recent_missed,
            "remaining_quantity": medication.quantity,
            "refill_at": medication.refill_at,
            "days_remaining": days_remaining,
            "compliance_percentage": compliance,
            "expected_doses_today": len(past_due_today),
            "taken_today": len(taken_today),
            "notification_enabled": medication.notification_enabled,
            "notify_service": medication.notify_service,
            "effective_notify_service": self.resolve_notify_service(medication),
            "food_note": medication.food_note,
            "keep_apart": list(medication.keep_apart),
            "keep_apart_minutes": medication.keep_apart_minutes,
            "conflicts": self.get_conflicts(medication),
            "paused": self.is_paused(medication.profile_id, now.date()),
            "caregiver_name": medication.caregiver_name,
            "caregiver_notify_service": medication.caregiver_notify_service,
            "confirmation_required": medication.confirmation_required,
            "caregiver_confirmation_needed": caregiver_confirmation_needed,
            "nfc_tag_id": medication.nfc_tag_id,
            "database_entry_id": medication.database_entry_id,
            "reminder_minutes": medication.reminder_minutes,
            "missed_after_minutes": medication.missed_after_minutes,
            "repeat_every_minutes": medication.repeat_every_minutes,
            "max_repeats": medication.max_repeats,
            "duplicate_guard_minutes": medication.duplicate_guard_minutes,
            "duplicate_dose_warning": duplicate_dose_warning,
            "snoozed_until": snoozed_until.isoformat() if snoozed_until else None,
            "skipped_occurrences": medication.skipped_occurrences,
            "stock_depletion_date": stock_depletion_date.isoformat() if stock_depletion_date else None,
            "stock_status": self._stock_status(medication, now, stock_depletion_date),
            "due_now": self._is_due_now(medication, now, state),
            "outstanding": outstanding is not None,
            "outstanding_time": outstanding.isoformat() if outstanding else None,
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
            "outstanding_count": sum(1 for item in snapshots if item["outstanding"]),
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
            if status == STATUS_ON_TRACK and snapshot["needs_refill"]:
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

    def get_today_doses(self) -> list[dict[str, Any]]:
        """Return today's scheduled doses with their status, for the panel."""
        now = dt_util.now()
        doses: list[dict[str, Any]] = []
        for medication in self.medications.values():
            state = self._match_state(medication, now)
            outstanding = self._outstanding_occurrence(medication, now, state)
            for occurrence in state.occurrences:
                if occurrence.date() != now.date():
                    continue
                doses.append(
                    {
                        "medication_id": medication.medication_id,
                        "medication_name": medication.name,
                        "profile_id": medication.profile_id,
                        "profile_name": medication.profile_name,
                        "dosage": medication.dosage,
                        "group_id": medication.group_id,
                        "group_name": self._group_name(medication),
                        "group_order": self.groups[medication.group_id].order if medication.group_id in self.groups else 999,
                        "sort_order": medication.sort_order,
                        "time": occurrence.strftime("%H:%M"),
                        "scheduled_at": occurrence.isoformat(),
                        "status": self._occurrence_status(medication, occurrence, now, state.matched),
                        "can_take": outstanding is not None and outstanding == occurrence,
                    }
                )
        doses.sort(
            key=lambda item: (
                item["scheduled_at"],
                item["profile_name"].lower(),
                item["group_order"],
                item["sort_order"],
                item["medication_name"].lower(),
            )
        )
        return doses

    def get_as_needed(self) -> list[dict[str, Any]]:
        """Return as-needed medications with how many doses were taken today."""
        now = dt_util.now()
        rows: list[dict[str, Any]] = []
        for medication in self.medications.values():
            if not medication.as_needed:
                continue
            taken_today = sum(
                1 for item in medication.dose_logs if dt_util.as_local(item.taken_at).date() == now.date()
            )
            at_limit = bool(medication.max_doses_per_day and taken_today >= medication.max_doses_per_day)
            rows.append(
                {
                    "medication_id": medication.medication_id,
                    "medication_name": medication.name,
                    "profile_id": medication.profile_id,
                    "profile_name": medication.profile_name,
                    "dosage": medication.dosage,
                    "doses_today": taken_today,
                    "max_doses_per_day": medication.max_doses_per_day,
                    "at_limit": at_limit,
                    "last_taken": medication.dose_logs[-1].taken_at.isoformat() if medication.dose_logs else None,
                    "duplicate_dose_warning": self._duplicate_dose_warning(medication, now),
                }
            )
        rows.sort(key=lambda item: (item["profile_name"].lower(), item["medication_name"].lower()))
        return rows

    def get_recent_logs(self, limit: int = 50, days: int | None = None) -> list[dict[str, Any]]:
        """Return the newest dose logs across all medications."""
        cutoff = dt_util.now() - timedelta(days=days) if days else None
        entries: list[dict[str, Any]] = []
        for medication in self.medications.values():
            logs = medication.dose_logs if cutoff else medication.dose_logs[-limit:]
            for dose_log in logs:
                if cutoff and dt_util.as_local(dose_log.taken_at) < cutoff:
                    continue
                entries.append(
                    {
                        "medication_id": medication.medication_id,
                        "medication_name": medication.name,
                        "profile_name": medication.profile_name,
                        "taken_at": dose_log.taken_at.isoformat(),
                        "source": dose_log.source,
                        "confirmed_by": dose_log.confirmed_by,
                        "taken_by": dose_log.taken_by,
                    }
                )
        entries.sort(key=lambda item: item["taken_at"], reverse=True)
        return entries[:limit]

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def get_pending_alerts(self) -> list[dict[str, Any]]:
        """Return due, missed, and refill alerts that still need notifying."""
        now = dt_util.now()
        alerts: list[dict[str, Any]] = []
        due_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        missed_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        refill_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        caregiver_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        escalation_alert_groups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
        quiet = self._in_quiet_hours(now)
        for medication in self.medications.values():
            if not medication.notification_enabled:
                continue

            state = self._match_state(medication, now)
            notify_service = self.resolve_notify_service(medication)

            due_schedule = self._current_due_schedule(medication, now, state)
            if due_schedule:
                marker = due_schedule.isoformat()
                is_repeat = False
                send_due = False
                if medication.last_due_notification != marker:
                    send_due = True
                elif (
                    medication.repeat_every_minutes > 0
                    and medication.due_repeat_count < 1 + medication.max_repeats
                    and medication.last_due_sent_at
                    and now >= datetime.fromisoformat(medication.last_due_sent_at)
                    + timedelta(minutes=medication.repeat_every_minutes)
                ):
                    send_due = True
                    is_repeat = True
                if send_due:
                    due_alert_groups[(medication.profile_id, marker, notify_service)].append(
                        {
                            "medication_id": medication.medication_id,
                            "profile_id": medication.profile_id,
                            "profile_name": medication.profile_name,
                            "medication_name": medication.name,
                            "dosage": medication.dosage,
                            "notify_service": notify_service,
                            "scheduled_time": due_schedule,
                            "display_time": self._effective_due_start(medication, due_schedule),
                            "food_note": medication.food_note,
                            "repeat": is_repeat,
                            **self._item_group(medication),
                        }
                    )

            missed_schedule = self._current_missed_schedule(medication, now, state)
            if missed_schedule and medication.last_missed_notification != missed_schedule.isoformat():
                missed_alert_groups[
                    (medication.profile_id, missed_schedule.isoformat(), notify_service)
                ].append(
                    {
                        "medication_id": medication.medication_id,
                        "profile_id": medication.profile_id,
                        "profile_name": medication.profile_name,
                        "medication_name": medication.name,
                        "dosage": medication.dosage,
                        "notify_service": notify_service,
                        "scheduled_time": missed_schedule,
                        **self._item_group(medication),
                    }
                )

            if medication.escalate_after_minutes > 0:
                escalation_service = medication.caregiver_notify_service or self.settings.get(
                    SETTING_ESCALATION_NOTIFY
                )
                overdue = self._outstanding_occurrence(medication, now, state)
                if escalation_service and overdue is not None and overdue <= now:
                    threshold = self._effective_due_start(medication, overdue) + timedelta(
                        minutes=medication.escalate_after_minutes
                    )
                    marker = overdue.isoformat()
                    if now >= threshold and medication.last_escalation_notification != marker:
                        escalation_alert_groups[(medication.profile_id, marker, escalation_service)].append(
                            {
                                "medication_id": medication.medication_id,
                                "profile_id": medication.profile_id,
                                "profile_name": medication.profile_name,
                                "medication_name": medication.name,
                                "dosage": medication.dosage,
                                "notify_service": escalation_service,
                                "scheduled_time": overdue,
                                **self._item_group(medication),
                            }
                        )

            # Refill reminders are not urgent, so they wait until quiet hours are over.
            if self._needs_refill(medication) and not quiet:
                refill_marker = now.date().isoformat()
                if medication.last_refill_notification != refill_marker:
                    remaining = medication.quantity if medication.quantity is not None else 0
                    refill_alert_groups[(medication.profile_id, refill_marker, notify_service)].append(
                        {
                            "medication_id": medication.medication_id,
                            "profile_id": medication.profile_id,
                            "profile_name": medication.profile_name,
                            "medication_name": medication.name,
                            "dosage": medication.dosage,
                            "remaining": remaining,
                            "days_left": self._days_remaining(medication),
                            "notify_service": notify_service,
                            "scheduled_time": None,
                        }
                    )
            if medication.confirmation_required and medication.caregiver_name and medication.dose_logs:
                latest_log = medication.dose_logs[-1]
                if (
                    latest_log.confirmed_by is None
                    and medication.last_caregiver_notification != latest_log.taken_at.isoformat()
                ):
                    caregiver_service = self.resolve_notify_service(medication, caregiver=True)
                    caregiver_alert_groups[
                        (medication.profile_id, latest_log.taken_at.isoformat(), caregiver_service)
                    ].append(
                        {
                            "medication_id": medication.medication_id,
                            "profile_id": medication.profile_id,
                            "profile_name": medication.profile_name,
                            "medication_name": medication.name,
                            "dosage": medication.dosage,
                            "caregiver_name": medication.caregiver_name,
                            "notify_service": caregiver_service,
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
        for grouped_escalation_medications in escalation_alert_groups.values():
            alerts.append(self._build_escalation_alert(grouped_escalation_medications))

        return alerts

    def alert_still_active(self, alert_type: str, medication_ids: Iterable[str]) -> bool:
        """Return whether an alert that was already sent still applies."""
        now = dt_util.now()
        for medication_id in medication_ids:
            medication = self.medications.get(medication_id)
            if medication is None:
                continue
            state = self._match_state(medication, now)
            if alert_type == "due" and self._current_due_schedule(medication, now, state):
                return True
            if alert_type == "missed" and self._current_missed_schedule(medication, now, state):
                return True
            if alert_type == "refill" and self._needs_refill(medication):
                return True
            if alert_type == "escalation" and self._outstanding_occurrence(medication, now, state):
                return True
            if (
                alert_type == "caregiver_confirmation"
                and medication.confirmation_required
                and medication.dose_logs
                and not medication.dose_logs[-1].confirmed_by
            ):
                return True
        return False

    async def async_mark_alert_sent(
        self,
        medication_id: str,
        alert_type: str,
        scheduled_time: datetime | None = None,
    ) -> None:
        """Persist notification markers to avoid duplicate alerts."""
        medication = self.medications.get(medication_id)
        if medication is None:
            return
        now = dt_util.now()
        if alert_type == "due" and scheduled_time:
            marker = scheduled_time.isoformat()
            if medication.last_due_notification == marker:
                medication.due_repeat_count += 1
            else:
                medication.due_repeat_count = 1
            medication.last_due_notification = marker
            medication.last_due_sent_at = now.isoformat()
        elif alert_type == "missed" and scheduled_time:
            medication.last_missed_notification = scheduled_time.isoformat()
        elif alert_type == "refill":
            medication.last_refill_notification = now.date().isoformat()
        elif alert_type == "caregiver_confirmation" and scheduled_time:
            medication.last_caregiver_notification = scheduled_time.isoformat()
        elif alert_type == "escalation" and scheduled_time:
            medication.last_escalation_notification = scheduled_time.isoformat()
        await self._async_save()

    # ------------------------------------------------------------------
    # 0.6.0: labels, pauses, interactions, backups, weekly summary
    # ------------------------------------------------------------------

    def _label(self, item: dict[str, Any]) -> str:
        """Medication name and dose for a notification line, with any food instruction."""
        text = f"{item['medication_name']} ({item['dosage']})"
        note = FOOD_NOTES.get(item.get("food_note") or "")
        return f"{text} - {note}" if note else text

    @staticmethod
    def _days_left_text(item: dict[str, Any]) -> str:
        days = item.get("days_left")
        return f" (about {days} day{'s' if days != 1 else ''} left)" if days is not None else ""

    def is_paused(self, profile_id: str, day: date) -> bool:
        """Return whether reminders are paused for a person on a calendar day."""
        iso = day.isoformat()
        for pause in self.settings.get(SETTING_PAUSES, []):
            if pause.get("profile_id") not in (None, profile_id):
                continue
            if pause["start"] <= iso <= pause["end"]:
                return True
        return False

    async def async_add_pause(
        self, *, end: str, start: str | None = None, profile_id: str | None = None
    ) -> None:
        """Pause reminders and missed-dose counting for a date range (inclusive)."""
        today = dt_util.now().date()
        start_date = self._parse_date(start, "start") if start else today
        end_date = self._parse_date(end, "end")
        if end_date is None or start_date is None:
            raise HomeAssistantError("Choose the last day of the pause.")
        if end_date < start_date:
            raise HomeAssistantError("The pause cannot end before it starts.")
        if (end_date - start_date).days > 365:
            raise HomeAssistantError("A pause can be at most a year long.")
        if profile_id and profile_id not in self.list_profiles():
            raise HomeAssistantError(f"Unknown person: {profile_id}")
        pauses = list(self.settings.get(SETTING_PAUSES, []))
        pauses.append(
            {"profile_id": profile_id or None, "start": start_date.isoformat(), "end": end_date.isoformat()}
        )
        self.settings[SETTING_PAUSES] = pauses
        await self._async_save()

    async def async_remove_pause(self, index: int | None = None, profile_id: str | None = None) -> None:
        """Remove one pause by position, or every pause that covers today for a person (or everyone)."""
        pauses = list(self.settings.get(SETTING_PAUSES, []))
        if index is not None:
            if index < 0 or index >= len(pauses):
                raise HomeAssistantError("That pause no longer exists.")
            pauses.pop(index)
        else:
            today = dt_util.now().date().isoformat()
            pauses = [
                p
                for p in pauses
                if not (p["start"] <= today <= p["end"] and (profile_id is None or p.get("profile_id") == profile_id))
            ]
        self.settings[SETTING_PAUSES] = pauses
        await self._async_save()

    def get_pauses_view(self) -> list[dict[str, Any]]:
        """Pauses that have not finished yet, for the panel."""
        today = dt_util.now().date().isoformat()
        names = self.list_profiles()
        rows = []
        for index, pause in enumerate(self.settings.get(SETTING_PAUSES, [])):
            if pause["end"] < today:
                continue
            rows.append(
                {
                    "index": index,
                    "profile_id": pause.get("profile_id"),
                    "profile_name": names.get(pause.get("profile_id"), "Everyone") if pause.get("profile_id") else "Everyone",
                    "start": pause["start"],
                    "end": pause["end"],
                    "active": pause["start"] <= today <= pause["end"],
                }
            )
        return rows

    @staticmethod
    def _minutes(schedule: str) -> int:
        return int(schedule[:2]) * 60 + int(schedule[3:5])

    def get_conflicts(self, medication: Medication) -> list[dict[str, Any]]:
        """Medications that are scheduled closer together than they should be."""
        if medication.as_needed:
            return []
        ids = set(medication.keep_apart) | {
            other.medication_id for other in self.medications.values() if medication.medication_id in other.keep_apart
        }
        ids.discard(medication.medication_id)
        conflicts = []
        for other_id in sorted(ids):
            other = self.medications.get(other_id)
            if other is None or other.as_needed:
                continue
            window = max(
                medication.keep_apart_minutes if other_id in medication.keep_apart else 0,
                other.keep_apart_minutes if medication.medication_id in other.keep_apart else 0,
            )
            gaps = []
            for a in medication.schedules:
                for b in other.schedules:
                    gap = abs(self._minutes(a) - self._minutes(b))
                    gaps.append(min(gap, 1440 - gap))
            if gaps and min(gaps) < window:
                conflicts.append(
                    {
                        "medication_id": other_id,
                        "medication_name": other.name,
                        "gap_minutes": min(gaps),
                        "required_minutes": window,
                    }
                )
        return conflicts

    def keep_apart_warnings(self, medication_id: str, now: datetime | None = None) -> list[str]:
        """Warnings for a dose that was just taken too close to one it should be kept apart from."""
        now = now or dt_util.now()
        medication = self._get_medication(medication_id)
        ids = set(medication.keep_apart) | {
            other.medication_id for other in self.medications.values() if medication_id in other.keep_apart
        }
        ids.discard(medication_id)
        warnings = []
        for other_id in sorted(ids):
            other = self.medications.get(other_id)
            if other is None or not other.dose_logs:
                continue
            window = max(
                medication.keep_apart_minutes if other_id in medication.keep_apart else 0,
                other.keep_apart_minutes if medication_id in other.keep_apart else 0,
            )
            ago = (now - dt_util.as_local(other.dose_logs[-1].taken_at)).total_seconds() / 60
            if 0 <= ago < window:
                warnings.append(
                    f"{other.name} was taken {int(ago)} minutes ago. Leave about {window} minutes between it "
                    f"and {medication.name}."
                )
        return warnings

    # ----------------------------------------------------------- backups

    def export_data(self) -> dict[str, Any]:
        """Everything needed to rebuild this installation."""
        return {
            "format": BACKUP_FORMAT,
            "version": VERSION,
            "exported_at": dt_util.now().isoformat(),
            "medications": [m.as_dict() for m in self.medications.values()],
            "groups": [g.as_dict() for g in self.groups.values()],
            "settings": deepcopy(self.settings),
        }

    async def async_import_data(self, data: Any) -> dict[str, int]:
        """Replace all data with the contents of a backup."""
        if not isinstance(data, dict) or data.get("format") != BACKUP_FORMAT:
            raise HomeAssistantError("That does not look like a Medication Tracker backup file.")
        try:
            medications = {
                item["medication_id"]: Medication.from_dict(item) for item in data.get("medications", [])
            }
            groups = {item["group_id"]: Group.from_dict(item) for item in data.get("groups", [])}
        except (KeyError, ValueError, TypeError) as err:
            raise HomeAssistantError("The backup file is damaged or incomplete.") from err
        settings = deepcopy(DEFAULT_SETTINGS)
        stored = data.get("settings")
        if isinstance(stored, dict):
            for key in DEFAULT_SETTINGS:
                if stored.get(key) is not None:
                    settings[key] = stored[key]
        for medication in medications.values():
            if medication.group_id and medication.group_id not in groups:
                medication.group_id = None
        await self._async_write_backup("before_restore")  # a safety copy of what is being replaced
        self.medications.clear()
        self.medications.update(medications)
        self.groups.clear()
        self.groups.update(groups)
        self.settings.clear()
        self.settings.update(settings)
        self._prune_old_logs()
        self._sync_groups()
        await self._async_save()
        return {"medications": len(medications), "groups": len(groups)}

    async def _async_write_backup(self, label: str) -> bool:
        """Write a backup file into the Home Assistant config folder. Never raises."""
        if not self.medications and not self.groups:
            return False
        try:
            folder = Path(self.hass.config.path(BACKUP_DIR))
            payload = json.dumps(self.export_data())
            name = f"medication_tracker_{label}.json"

            def _write() -> None:
                folder.mkdir(parents=True, exist_ok=True)
                (folder / name).write_text(payload, encoding="utf-8")
                daily = sorted(folder.glob("medication_tracker_20??-??-??.json"))
                for old in daily[:-BACKUP_KEEP]:
                    old.unlink()

            await self.hass.async_add_executor_job(_write)
            return True
        except Exception:  # noqa: BLE001 - a backup problem must never stop reminders
            _LOGGER.warning("Could not write a Medication Tracker backup", exc_info=True)
            return False

    async def async_auto_backup(self) -> None:
        """Write one backup file per day (the last two weeks are kept)."""
        today = dt_util.now().date()
        if getattr(self, "_last_backup_date", None) == today:
            return
        self._last_backup_date = today
        await self._async_write_backup(today.isoformat())

    # ---------------------------------------------------- weekly summary

    def get_weekly_summary(self, now: datetime | None = None) -> dict[str, Any] | None:
        """Adherence for the last seven full days, per person."""
        now = now or dt_util.now()
        end = now.date() - timedelta(days=1)
        start = end - timedelta(days=6)
        people: dict[str, dict[str, Any]] = {}
        for medication in self.medications.values():
            if medication.as_needed:
                continue
            state = self._match_state(medication, now)
            for occurrence in state.occurrences:
                if occurrence.date() < start or occurrence.date() > end:
                    continue
                person = people.setdefault(
                    medication.profile_id,
                    {"name": medication.profile_name, "expected": 0, "taken": 0, "skipped": 0, "missed": [], "low": []},
                )
                if occurrence.isoformat() in medication.skipped_occurrences:
                    person["skipped"] += 1
                    continue
                person["expected"] += 1
                if occurrence in state.matched:
                    person["taken"] += 1
                else:
                    person["missed"].append(f"{medication.name} ({occurrence.strftime('%a')})")
        for medication in self.medications.values():
            if self._needs_refill(medication):
                person = people.setdefault(
                    medication.profile_id,
                    {"name": medication.profile_name, "expected": 0, "taken": 0, "skipped": 0, "missed": [], "low": []},
                )
                person["low"].append(medication.name)
        if not people:
            return None
        lines = []
        for person in sorted(people.values(), key=lambda p: p["name"].lower()):
            if person["expected"]:
                pct = round(100 * person["taken"] / person["expected"])
                line = f"{person['name']}: {person['taken']} of {person['expected']} doses taken ({pct}%)"
            else:
                line = f"{person['name']}: nothing was scheduled"
            if person["missed"]:
                shown = ", ".join(person["missed"][:6])
                more = len(person["missed"]) - 6
                line += f". Missed: {shown}{f' and {more} more' if more > 0 else ''}"
            if person["low"]:
                line += f". Running low: {', '.join(sorted(person['low']))}"
            lines.append(line)
        return {"people": list(people.values()), "message": "Last week:\n" + "\n".join(lines)}

    def weekly_summary_due(self, now: datetime | None = None) -> bool:
        """True once on the chosen weekday from 09:00, if a summary phone is set."""
        now = now or dt_util.now()
        if not self.settings.get(SETTING_WEEKLY_SERVICE):
            return False
        if now.weekday() != int(self.settings.get(SETTING_WEEKLY_DAY, 6)) or now.hour < 9:
            return False
        return self.settings.get(SETTING_LAST_WEEKLY) != now.date().isoformat()

    async def async_mark_weekly_sent(self, day: date) -> None:
        self.settings[SETTING_LAST_WEEKLY] = day.isoformat()
        await self._async_save()

    async def _async_save(self) -> None:
        """Persist medication state."""
        await self.store.async_save(self.medications, self.settings, self.groups)

    def _get_medication(self, medication_id: str) -> Medication:
        """Fetch a medication or raise a service-friendly error."""
        try:
            return self.medications[medication_id]
        except KeyError as err:
            raise HomeAssistantError(f"Unknown medication_id: {medication_id}") from err

    # ------------------------------------------------------------------
    # Schedule maths
    # ------------------------------------------------------------------

    def _parse_date(self, value: str, label: str) -> date | None:
        """Parse an ISO date; an empty value means no date."""
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError as err:
            raise HomeAssistantError(f"{label} must be a date like 2026-12-31.") from err

    def _in_quiet_hours(self, now: datetime) -> bool:
        """Return whether the configured quiet hours are active."""
        start = self.settings.get(SETTING_QUIET_START)
        end = self.settings.get(SETTING_QUIET_END)
        if not start or not end:
            return False
        try:
            start_time, end_time = time.fromisoformat(start), time.fromisoformat(end)
        except ValueError:
            return False
        current = now.timetz().replace(tzinfo=None)
        if start_time <= end_time:
            return start_time <= current < end_time
        return current >= start_time or current < end_time

    def _doses_per_day(self, medication: Medication) -> float:
        """Average scheduled doses per day, allowing for weekdays and interval schedules."""
        if medication.as_needed or not medication.schedules:
            return 0.0
        day_fraction = len(medication.days_of_week) / 7 if medication.days_of_week else 1.0
        return len(medication.schedules) * day_fraction / max(medication.interval_days, 1)

    def _normalize_schedules(self, schedules: list[str], allow_empty: bool = False) -> list[str]:
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

        if not normalized and not allow_empty:
            raise HomeAssistantError("At least one schedule time is required.")

        return sorted(normalized)

    def _normalize_days(self, days_of_week: list[int] | None) -> list[int] | None:
        """Normalize a weekday list (0 = Monday). None or all seven days means every day."""
        if not days_of_week:
            return None
        try:
            days = sorted({int(day) for day in days_of_week})
        except (TypeError, ValueError) as err:
            raise HomeAssistantError("days_of_week must be numbers from 0 (Mon) to 6 (Sun).") from err
        if any(day < 0 or day > 6 for day in days):
            raise HomeAssistantError("days_of_week must be numbers from 0 (Mon) to 6 (Sun).")
        return None if len(days) == 7 else days

    def _combine(self, target_date: date, schedule: str) -> datetime:
        """Combine a date and schedule into a timezone-aware datetime."""
        scheduled_time = time.fromisoformat(schedule)
        return datetime.combine(target_date, scheduled_time, tzinfo=dt_util.DEFAULT_TIME_ZONE)

    def _is_scheduled_day(self, medication: Medication, day: date) -> bool:
        """Return whether the medication is scheduled on a calendar day."""
        if medication.as_needed:
            return False
        if medication.end_date and day > medication.end_date:
            return False
        if self.is_paused(medication.profile_id, day):
            return False
        if medication.interval_days > 1:
            anchor = medication.anchor_date or medication.start_date
            if (day - anchor).days % medication.interval_days:
                return False
        return not medication.days_of_week or day.weekday() in medication.days_of_week

    def _created_at(self, medication: Medication) -> datetime | None:
        """Return when the medication was created, if known."""
        if not medication.created_at:
            return None
        try:
            return datetime.fromisoformat(medication.created_at)
        except ValueError:
            return None

    def _next_scheduled_dose(self, medication: Medication, now: datetime) -> datetime | None:
        """Return the next scheduled dose datetime."""
        for day_offset in range(0, MAX_INTERVAL_DAYS + 2):
            candidate_date = now.date() + timedelta(days=day_offset)
            if not self._is_scheduled_day(medication, candidate_date):
                continue
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
        per_day = self._doses_per_day(medication)
        if per_day <= 0:
            return None
        return math.floor(medication.quantity / per_day)

    def _scheduled_occurrences(self, medication: Medication, start_date: date, end_date: date) -> list[datetime]:
        """Return every scheduled occurrence in a date range."""
        created = self._created_at(medication)
        occurrences: list[datetime] = []
        current_date = start_date
        while current_date <= end_date:
            if self._is_scheduled_day(medication, current_date):
                for schedule in medication.schedules:
                    occurrence = self._combine(current_date, schedule)
                    if created is not None and occurrence < created:
                        continue
                    occurrences.append(occurrence)
            current_date += timedelta(days=1)
        return sorted(occurrences)

    def _window_starts(self, occurrences: list[datetime]) -> list[datetime]:
        """Return the earliest time a dose can count for each occurrence."""
        starts: list[datetime] = []
        for index, occurrence in enumerate(occurrences):
            gap = timedelta(hours=24) if index == 0 else occurrence - occurrences[index - 1]
            early = min(timedelta(minutes=EARLY_WINDOW_MINUTES), gap / 2)
            starts.append(occurrence - early)
        return starts

    def _match_state(self, medication: Medication, now: datetime) -> _MatchState:
        """Match logged doses to scheduled occurrences.

        Each occurrence owns the period from shortly before it (so an early dose counts)
        until shortly before the next occurrence (so a late dose still counts for it).
        """
        history_start = max(medication.start_date, now.date() - timedelta(days=HISTORY_WINDOW_DAYS))
        occurrences = self._scheduled_occurrences(
            medication,
            history_start,
            now.date() + timedelta(days=2),
        )
        starts = self._window_starts(occurrences)
        matched: set[datetime] = set()
        for logged_at in sorted(dt_util.as_local(dose_log.taken_at) for dose_log in medication.dose_logs):
            index = bisect_right(starts, logged_at) - 1
            if index >= 0:
                matched.add(occurrences[index])
        return _MatchState(occurrences, starts, matched)

    def _matched_occurrences(
        self,
        medication: Medication,
        occurrences: list[datetime],
        now: datetime | None = None,
    ) -> list[datetime]:
        """Return the given occurrences that have a matching dose."""
        state = self._match_state(medication, now or dt_util.now())
        return [occurrence for occurrence in occurrences if occurrence in state.matched]

    def _outstanding_occurrence(
        self,
        medication: Medication,
        now: datetime,
        state: _MatchState | None = None,
    ) -> datetime | None:
        """Return the occurrence a dose logged right now would be for, if it still needs one."""
        state = state or self._match_state(medication, now)
        index = bisect_right(state.window_starts, now) - 1
        if index < 0:
            return None
        occurrence = state.occurrences[index]
        if occurrence in state.matched or occurrence.isoformat() in medication.skipped_occurrences:
            return None
        if now - occurrence > LATE_WINDOW:
            return None
        return occurrence

    def _current_due_schedule(
        self,
        medication: Medication,
        now: datetime,
        state: _MatchState | None = None,
    ) -> datetime | None:
        """Return the currently due schedule inside the reminder window."""
        state = state or self._match_state(medication, now)
        for scheduled_time in state.occurrences:
            if scheduled_time.date() != now.date():
                continue
            if scheduled_time.isoformat() in medication.skipped_occurrences:
                continue
            effective_due_start = self._effective_due_start(medication, scheduled_time)
            due_time = effective_due_start + timedelta(minutes=medication.reminder_minutes)
            if effective_due_start <= now <= due_time:
                if scheduled_time in state.matched:
                    continue
                return scheduled_time
        return None

    def _past_missed_threshold(self, medication: Medication, occurrence: datetime, now: datetime) -> bool:
        """Return whether an occurrence has passed its missed-dose threshold."""
        effective_due_start = self._effective_due_start(medication, occurrence)
        return now >= effective_due_start + timedelta(minutes=medication.missed_after_minutes)

    def _current_missed_schedule(
        self,
        medication: Medication,
        now: datetime,
        state: _MatchState | None = None,
    ) -> datetime | None:
        """Return the most recent missed occurrence from the last day, if any."""
        state = state or self._match_state(medication, now)
        for occurrence in reversed(state.occurrences):
            if occurrence > now:
                continue
            if now - occurrence > timedelta(hours=24):
                break
            if occurrence in state.matched or occurrence.isoformat() in medication.skipped_occurrences:
                continue
            if self._past_missed_threshold(medication, occurrence, now):
                return occurrence
        return None

    def _recent_missed(self, medication: Medication, now: datetime, state: _MatchState) -> bool:
        """Return whether a dose from the last day was missed."""
        return self._current_missed_schedule(medication, now, state) is not None

    def _is_due_now(self, medication: Medication, now: datetime, state: _MatchState | None = None) -> bool:
        """Return whether a medication is inside its due window."""
        return self._current_due_schedule(medication, now, state) is not None

    def _needs_refill(self, medication: Medication) -> bool:
        """Return whether the medication has crossed the refill threshold."""
        if medication.quantity is None or medication.refill_at is None:
            return False
        return medication.quantity <= medication.refill_at

    def _missed_doses(self, medication: Medication, now: datetime, state: _MatchState) -> int:
        """Count scheduled doses that have passed their missed threshold without a matching log."""
        missed = 0
        for occurrence in state.occurrences:
            if occurrence.date() > now.date():
                break
            if occurrence in state.matched:
                continue
            if occurrence.isoformat() in medication.skipped_occurrences:
                continue
            if self._past_missed_threshold(medication, occurrence, now):
                missed += 1
        return missed

    def _occurrence_status(
        self,
        medication: Medication,
        occurrence: datetime,
        now: datetime,
        matched: set[datetime],
    ) -> str:
        """Return the status of one scheduled occurrence."""
        if occurrence.isoformat() in medication.skipped_occurrences:
            return STATUS_SKIPPED
        if occurrence in matched:
            return STATUS_TAKEN

        effective_due_start = self._effective_due_start(medication, occurrence)

        if now >= effective_due_start + timedelta(minutes=medication.missed_after_minutes):
            return STATUS_MISSED
        if occurrence <= now < effective_due_start:
            return STATUS_SNOOZED
        if effective_due_start <= now <= effective_due_start + timedelta(minutes=medication.reminder_minutes):
            return STATUS_DUE
        return STATUS_ON_TRACK

    def _schedule_statuses(self, medication: Medication, now: datetime, days_ahead: int = 30) -> dict[str, str]:
        """Return day-and-time specific statuses for upcoming scheduled doses."""
        end_date = now.date() + timedelta(days=max(days_ahead - 1, 0))
        occurrences = [
            occurrence
            for occurrence in self._scheduled_occurrences(medication, now.date(), end_date)
        ]
        matched = self._match_state(medication, now).matched
        return {
            occurrence.strftime("%Y-%m-%dT%H:%M"): self._occurrence_status(medication, occurrence, now, matched)
            for occurrence in occurrences
        }

    def _current_display_status(self, medication: Medication, now: datetime) -> str:
        """Return a card-friendly status based on today's scheduled doses."""
        state = self._match_state(medication, now)
        today_occurrences = [occurrence for occurrence in state.occurrences if occurrence.date() == now.date()]
        if not today_occurrences:
            return STATUS_ON_TRACK

        has_taken_today = False
        for occurrence in today_occurrences:
            status = self._occurrence_status(medication, occurrence, now, state.matched)
            if status == STATUS_TAKEN:
                has_taken_today = True
            elif status in (STATUS_MISSED, STATUS_SNOOZED, STATUS_DUE):
                return status

        if has_taken_today:
            return STATUS_TAKEN

        return STATUS_ON_TRACK

    # ------------------------------------------------------------------
    # Alert builders
    # ------------------------------------------------------------------

    def _build_actions(self, kind: str, items: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Build mobile notification actions for one or more medications.

        Android shows up to three actions. One medication gets Taken / Snooze / Skip. A set of
        medications gets All taken (for the group, or for the person) and Snooze; tapping the
        notification opens the panel, where each item can be ticked off individually.
        """
        if len(items) == 1:
            medication_id = items[0]["medication_id"]
            actions = [
                {
                    "action": f"{ACTION_CONFIRMED_PREFIX}{medication_id}",
                    "title": "Taken" if kind == "due" else "Mark taken",
                }
            ]
            if kind == "due":
                actions.append({"action": f"{ACTION_SNOOZE_PREFIX}{medication_id}", "title": "Snooze 10 min"})
            actions.append({"action": f"{ACTION_SKIP_PREFIX}{medication_id}", "title": "Skip"})
            return actions

        group_ids = {item.get("group_id") for item in items}
        single_group = len(group_ids) == 1 and None not in group_ids
        if single_group:
            group_id = next(iter(group_ids))
            actions = [{"action": f"{ACTION_GROUP_PREFIX}{group_id}", "title": "All taken"}]
            snooze = {"action": f"{ACTION_GROUP_SNOOZE_PREFIX}{group_id}", "title": "Snooze 10 min"}
        else:
            profile_id = items[0]["profile_id"]
            actions = [{"action": f"{ACTION_ALL_PREFIX}{profile_id}", "title": "All taken"}]
            snooze = {"action": f"{ACTION_SNOOZE_ALL_PREFIX}{profile_id}", "title": "Snooze 10 min"}
        if kind == "due":
            actions.append(snooze)
            return actions
        for item in items[:2]:
            actions.append(
                {
                    "action": f"{ACTION_CONFIRMED_PREFIX}{item['medication_id']}",
                    "title": f"Taken: {item['medication_name']}",
                }
            )
        return actions

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
        is_repeat = all(item.get("repeat") for item in sorted_due_medications)
        prefix = "Reminder: " if is_repeat else ""
        when = display_time.strftime("%H:%M")
        group_ids = {item.get("group_id") for item in sorted_due_medications}
        single_group = len(group_ids) == 1 and None not in group_ids
        title = "Medication Tracker"

        if len(sorted_due_medications) == 1:
            message = (
                f"{prefix}{first['profile_name']} is due to take {self._label(first)} at {when}."
            )
        elif single_group:
            title = first["group_name"] or title
            lines = "\n".join(f"- {self._label(item)}" for item in sorted_due_medications)
            message = (
                f"{prefix}{first['profile_name']}: {len(sorted_due_medications)} to take at {when}:\n{lines}"
            )
        else:
            sections: dict[str | None, list[dict[str, Any]]] = {}
            for item in sorted_due_medications:
                sections.setdefault(item.get("group_name"), []).append(item)
            if len(sections) == 1:
                lines = "\n".join(f"- {self._label(i)}" for i in sorted_due_medications)
            else:
                blocks = []
                for group_name in sorted(sections, key=lambda g: (g is None, (g or "").lower())):
                    heading = f"{group_name}:" if group_name else "Other:"
                    rows = "\n".join(f"- {self._label(i)}" for i in sections[group_name])
                    blocks.append(f"{heading}\n{rows}")
                lines = "\n".join(blocks)
            message = (
                f"{prefix}{first['profile_name']} is due to take {len(sorted_due_medications)} medications "
                f"at {when}:\n{lines}"
            )

        return {
            "type": "due",
            "medication_id": first["medication_id"],
            "medication_ids": medication_ids,
            "notify_service": first["notify_service"],
            "scheduled_time": scheduled_time,
            "title": title,
            "message": message,
            "repeat": is_repeat,
            "actions": self._build_actions("due", sorted_due_medications),
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
            "actions": self._build_actions("missed", sorted_missed_medications),
            "notification_suffix": "_".join(medication_ids) if len(medication_ids) > 1 else None,
        }

    def _build_escalation_alert(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the alert sent to a caregiver when a dose is still not taken."""
        items = sorted(items, key=lambda item: (item["scheduled_time"], item["medication_name"].lower()))
        first = items[0]
        ids = [item["medication_id"] for item in items]
        when = first["scheduled_time"].strftime("%H:%M")
        if len(items) == 1:
            message = (
                f"{first['profile_name']} has not taken {first['medication_name']} "
                f"({first['dosage']}) due at {when}. Please check on them."
            )
        else:
            lines = "\n".join(f"- {item['medication_name']} ({item['dosage']})" for item in items)
            message = (
                f"{first['profile_name']} has not taken {len(items)} medications due at {when}. "
                f"Please check on them:\n{lines}"
            )
        return {
            "type": "escalation",
            "medication_id": first["medication_id"],
            "medication_ids": ids,
            "notify_service": first["notify_service"],
            "scheduled_time": first["scheduled_time"],
            "message": message,
            "actions": self._build_actions("missed", items),
            "notification_suffix": "_".join(ids) if len(ids) > 1 else None,
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
        per_day = self._doses_per_day(medication)
        if per_day <= 0:
            return None
        # Anchor to the start of the day so the date does not creep forward every minute.
        anchor = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return anchor + timedelta(days=medication.quantity / per_day)

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
                f"with {first['remaining']:g} doses remaining{self._days_left_text(first)}."
            )
        else:
            medication_lines = "\n".join(
                f"- {item['medication_name']} ({item['dosage']}): {item['remaining']:g} doses remaining{self._days_left_text(item)}"
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
