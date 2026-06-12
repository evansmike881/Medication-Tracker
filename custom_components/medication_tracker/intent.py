"""Assist intent handlers for Medication Tracker."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import DOMAIN


async def async_register_intents(hass: HomeAssistant) -> None:
    """Register Medication Tracker intents once."""
    if hass.data[DOMAIN].get("intents_registered"):
        return
    intent.async_register(hass, MedicationStatusIntent(hass))
    intent.async_register(hass, MedicationLogIntent(hass))
    intent.async_register(hass, MedicationDueIntent(hass))
    intent.async_register(hass, MedicationRefillIntent(hass))
    hass.data[DOMAIN]["intents_registered"] = True


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Home Assistant intent platform hook."""
    await async_register_intents(hass)


class MedicationBaseIntent(intent.IntentHandler):
    """Shared helper methods for medication intents."""

    platform = DOMAIN

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the handler."""
        self.hass = hass

    @property
    def _runtime_data(self) -> dict:
        for key, value in self.hass.data[DOMAIN].items():
            if key == "logger":
                continue
            if isinstance(value, dict) and "manager" in value:
                return value
        raise intent.IntentHandleError("Medication Tracker is not fully initialized yet.")

    @property
    def _manager(self):
        return self._runtime_data["manager"]

    def _normalize_slot(self, slot_value) -> str | None:
        """Return a normalized string from a slot."""
        if slot_value is None:
            return None
        if isinstance(slot_value, dict):
            value = slot_value.get("value")
        else:
            value = slot_value
        if not value:
            return None
        return str(value).strip()

    def _find_medication(self, medication_name: str, profile_name: str | None = None):
        """Find a medication by spoken name and optional profile."""
        lookup = medication_name.casefold()
        profile_lookup = profile_name.casefold() if profile_name else None

        candidates = list(self._manager.list_medications())
        if profile_lookup:
            profile_filtered = [
                medication
                for medication in candidates
                if medication.profile_name.casefold() == profile_lookup
                or profile_lookup in medication.profile_name.casefold()
            ]
            if profile_filtered:
                candidates = profile_filtered

        for medication in candidates:
            if medication.name.casefold() == lookup:
                return medication
        for medication in candidates:
            if lookup in medication.name.casefold():
                return medication
        return None

    def _format_time(self, value: str | None) -> str | None:
        """Return a spoken time from an ISO datetime string."""
        if not value:
            return None
        return value[11:16]

    def _snapshot_rows(self, medications: Iterable) -> list[dict]:
        """Return snapshots for a medication iterable."""
        return [self._manager.get_snapshot(medication.medication_id) for medication in medications]


class MedicationStatusIntent(MedicationBaseIntent):
    """Answer medication status questions."""

    intent_type = "MedicationStatusIntent"
    slot_schema = {"medication": str, "profile": str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        response = intent_obj.create_response()
        medication_name = self._normalize_slot(intent_obj.slots.get("medication"))
        profile_name = self._normalize_slot(intent_obj.slots.get("profile"))

        if not medication_name:
            response.async_set_speech("Tell me which medication you want to check.")
            return response

        medication = self._find_medication(medication_name, profile_name)
        if medication is None:
            if profile_name:
                response.async_set_speech(
                    f"I could not find a medication called {medication_name} for {profile_name}."
                )
            else:
                response.async_set_speech(f"I could not find a medication called {medication_name}.")
            return response

        snapshot = self._manager.get_snapshot(medication.medication_id)
        if snapshot["taken_today"] > 0 and snapshot["expected_doses_today"] == 0:
            response.async_set_speech(
                f"Yes, {snapshot['profile_name']} has already taken {snapshot['medication_name']} today."
            )
            return response

        if snapshot["taken_today"] >= snapshot["expected_doses_today"] and snapshot["expected_doses_today"] > 0:
            response.async_set_speech(
                f"Yes, {snapshot['profile_name']} has taken {snapshot['medication_name']} for the current schedule."
            )
            return response

        if snapshot["taken_today"] > 0 and snapshot["expected_doses_today"] > snapshot["taken_today"]:
            next_time = self._format_time(snapshot["next_dose"])
            extra = f" The next dose is at {next_time}." if next_time else ""
            response.async_set_speech(
                f"{snapshot['profile_name']} has taken {snapshot['medication_name']} today, "
                f"but another scheduled dose is still due later.{extra}"
            )
            return response

        if snapshot["next_dose"]:
            next_time = self._format_time(snapshot["next_dose"])
            response.async_set_speech(
                f"No, {snapshot['profile_name']} still needs {snapshot['medication_name']}. "
                f"The next dose is scheduled for {next_time}."
            )
            return response

        response.async_set_speech(
            f"{snapshot['profile_name']} has no upcoming dose scheduled for {snapshot['medication_name']}."
        )
        return response


class MedicationLogIntent(MedicationBaseIntent):
    """Log a medication dose from Assist."""

    intent_type = "MedicationLogIntent"
    slot_schema = {"medication": str, "profile": str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        response = intent_obj.create_response()
        medication_name = self._normalize_slot(intent_obj.slots.get("medication"))
        profile_name = self._normalize_slot(intent_obj.slots.get("profile"))

        if not medication_name:
            response.async_set_speech("Tell me which medication you want to log.")
            return response

        medication = self._find_medication(medication_name, profile_name)
        if medication is None:
            if profile_name:
                response.async_set_speech(
                    f"I could not find a medication called {medication_name} for {profile_name}."
                )
            else:
                response.async_set_speech(f"I could not find a medication called {medication_name}.")
            return response

        runtime_data = self._runtime_data
        await runtime_data["manager"].async_log_dose(medication.medication_id, source="assist")
        runtime_data["alert_engine"].dismiss_for_medication(medication.medication_id)
        await runtime_data["coordinator"].async_request_refresh()
        response.async_set_speech(f"Logged {medication.name} for {medication.profile_name} as taken.")
        return response


class MedicationDueIntent(MedicationBaseIntent):
    """Answer due-medication questions."""

    intent_type = "MedicationDueIntent"
    slot_schema = {"profile": str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        response = intent_obj.create_response()
        profile_name = self._normalize_slot(intent_obj.slots.get("profile"))

        medications = list(self._manager.list_medications())
        if profile_name:
            medications = [
                medication
                for medication in medications
                if profile_name.casefold() == medication.profile_name.casefold()
                or profile_name.casefold() in medication.profile_name.casefold()
            ]
            if not medications:
                response.async_set_speech(f"I could not find a person or pet called {profile_name}.")
                return response

        snapshots = [self._manager.get_snapshot(medication.medication_id) for medication in medications]
        due_now = [item for item in snapshots if item["due_now"]]
        next_due = sorted(
            [item for item in snapshots if item["next_dose"]],
            key=lambda item: item["next_dose"],
        )

        if due_now:
            due_names = ", ".join(f"{item['medication_name']} for {item['profile_name']}" for item in due_now[:4])
            if len(due_now) == 1:
                response.async_set_speech(f"Due right now: {due_names}.")
            else:
                response.async_set_speech(f"Due right now: {due_names}.")
            return response

        if next_due:
            item = next_due[0]
            next_time = self._format_time(item["next_dose"])
            response.async_set_speech(
                f"The next scheduled medication is {item['medication_name']} for {item['profile_name']} at {next_time}."
            )
            return response

        if profile_name:
            response.async_set_speech(f"There are no upcoming medications scheduled for {profile_name}.")
        else:
            response.async_set_speech("There are no upcoming medications scheduled right now.")
        return response


class MedicationRefillIntent(MedicationBaseIntent):
    """Answer refill-status questions."""

    intent_type = "MedicationRefillIntent"
    slot_schema = {"profile": str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        response = intent_obj.create_response()
        profile_name = self._normalize_slot(intent_obj.slots.get("profile"))

        medications = list(self._manager.list_medications())
        if profile_name:
            medications = [
                medication
                for medication in medications
                if profile_name.casefold() == medication.profile_name.casefold()
                or profile_name.casefold() in medication.profile_name.casefold()
            ]
            if not medications:
                response.async_set_speech(f"I could not find a person or pet called {profile_name}.")
                return response

        snapshots = [self._manager.get_snapshot(medication.medication_id) for medication in medications]
        low_stock = [item for item in snapshots if item["needs_refill"]]

        if low_stock:
            items = ", ".join(f"{item['medication_name']} for {item['profile_name']}" for item in low_stock[:4])
            response.async_set_speech(f"These medications need refills: {items}.")
            return response

        if profile_name:
            response.async_set_speech(f"{profile_name} does not have any medications needing a refill right now.")
        else:
            response.async_set_speech("No medications need a refill right now.")
        return response
