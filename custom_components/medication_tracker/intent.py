"""Assist intent handlers for Medication Tracker."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import DOMAIN


async def async_register_intents(hass: HomeAssistant) -> None:
    """Register Medication Tracker intents once."""
    if hass.data[DOMAIN].get("intents_registered"):
        return
    intent.async_register(hass, MedicationStatusIntent(hass))
    intent.async_register(hass, MedicationLogIntent(hass))
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
    def _manager(self):
        entry_ids = [key for key in self.hass.data[DOMAIN] if key not in {"logger", "intents_registered"}]
        return self.hass.data[DOMAIN][entry_ids[0]]["manager"]

    def _find_medication(self, medication_name: str):
        """Find a medication by spoken name."""
        lookup = medication_name.casefold()
        for medication in self._manager.list_medications():
            if medication.name.casefold() == lookup:
                return medication
        for medication in self._manager.list_medications():
            if lookup in medication.name.casefold():
                return medication
        return None


class MedicationStatusIntent(MedicationBaseIntent):
    """Answer medication status questions."""

    intent_type = "MedicationStatusIntent"
    slot_schema = {"medication": str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        response = intent_obj.create_response()
        medication_name = intent_obj.slots["medication"]["value"]
        medication = self._find_medication(medication_name)
        if medication is None:
            response.async_set_speech(f"I could not find a medication called {medication_name}.")
            return response

        snapshot = self._manager.get_snapshot(medication.medication_id)
        if snapshot["taken_today"] >= snapshot["expected_doses_today"] and snapshot["expected_doses_today"] > 0:
            response.async_set_speech(
                f"Yes, {snapshot['profile_name']} has taken {snapshot['medication_name']} for the current schedule."
            )
            return response

        if snapshot["next_dose"]:
            next_time = snapshot["next_dose"][11:16]
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
    slot_schema = {"medication": str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        response = intent_obj.create_response()
        medication_name = intent_obj.slots["medication"]["value"]
        medication = self._find_medication(medication_name)
        if medication is None:
            response.async_set_speech(f"I could not find a medication called {medication_name}.")
            return response

        runtime_data = self.hass.data[DOMAIN][
            [key for key in self.hass.data[DOMAIN] if key not in {"logger", "intents_registered"}][0]
        ]
        await runtime_data["manager"].async_log_dose(medication.medication_id)
        runtime_data["alert_engine"].dismiss_for_medication(medication.medication_id)
        await runtime_data["coordinator"].async_request_refresh()
        response.async_set_speech(f"Logged {medication.name} as taken.")
        return response
