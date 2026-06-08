"""Medication Tracker integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .alerts import MedicationAlertEngine
from .const import (
    ATTR_MEDICATION_ID,
    ATTR_NOTIFICATION_ENABLED,
    ATTR_NOTIFY_SERVICE,
    ATTR_NFC_TAG_ID,
    ATTR_PROFILE_ID,
    ATTR_PROFILE_NAME,
    ATTR_QUANTITY,
    ATTR_REFILL_AT,
    ATTR_REMINDER_MINUTES,
    ATTR_SCHEDULES,
    ATTR_TAKEN_AT,
    ATTR_DATABASE_ENTRY_ID,
    ATTR_MISSED_AFTER_MINUTES,
    ATTR_DOSAGE,
    ATTR_MEDICATION_NAME,
    ATTR_NOTES,
    DOMAIN,
    EVENT_NFC_LOGGED,
    DEFAULT_MISSED_AFTER_MINUTES,
    DEFAULT_REMINDER_MINUTES,
    PLATFORMS,
    SIGNAL_MEDICATIONS_UPDATED,
)
from .coordinator import MedicationTrackerCoordinator
from .intent import async_register_intents
from .manager import MedicationTrackerManager

LOGGER = logging.getLogger(__name__)

SERVICE_ADD_MEDICATION = "add_medication"
SERVICE_LOG_DOSE = "log_dose"
SERVICE_REFILL_MEDICATION = "refill_medication"
SERVICE_REMOVE_MEDICATION = "remove_medication"

ADD_MEDICATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PROFILE_ID): cv.string,
        vol.Required(ATTR_PROFILE_NAME): cv.string,
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Required(ATTR_MEDICATION_NAME): cv.string,
        vol.Required(ATTR_DOSAGE): cv.string,
        vol.Required(ATTR_SCHEDULES): vol.All([cv.string], vol.Length(min=1)),
        vol.Optional(ATTR_QUANTITY): vol.Coerce(float),
        vol.Optional(ATTR_REFILL_AT): vol.Coerce(float),
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional(ATTR_DATABASE_ENTRY_ID): cv.string,
        vol.Optional(ATTR_NFC_TAG_ID): cv.string,
        vol.Optional(ATTR_NOTIFICATION_ENABLED, default=True): cv.boolean,
        vol.Optional(ATTR_NOTIFY_SERVICE): cv.string,
        vol.Optional(ATTR_REMINDER_MINUTES, default=DEFAULT_REMINDER_MINUTES): vol.Coerce(int),
        vol.Optional(ATTR_MISSED_AFTER_MINUTES, default=DEFAULT_MISSED_AFTER_MINUTES): vol.Coerce(int),
    }
)

LOG_DOSE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Optional(ATTR_TAKEN_AT): cv.datetime,
    }
)

REFILL_MEDICATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Required(ATTR_QUANTITY): vol.Coerce(float),
    }
)

REMOVE_MEDICATION_SCHEMA = vol.Schema({vol.Required(ATTR_MEDICATION_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration domain."""
    hass.data.setdefault(DOMAIN, {"logger": LOGGER})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Medication Tracker from a config entry."""
    manager = MedicationTrackerManager(hass)
    await manager.async_initialize()

    alert_engine = MedicationAlertEngine(hass, manager)
    coordinator = MedicationTrackerCoordinator(hass, manager, alert_engine)
    hass.data[DOMAIN][entry.entry_id] = {
        "manager": manager,
        "coordinator": coordinator,
        "alert_engine": alert_engine,
    }

    await async_register_intents(hass)
    await _async_register_services(hass)
    entry.async_on_unload(
        hass.bus.async_listen("tag_scanned", lambda event: hass.async_create_task(_async_handle_tag_scanned(hass, event)))
    )
    entry.async_on_unload(
        hass.bus.async_listen(
            "mobile_app_notification_action",
            lambda event: hass.async_create_task(_async_handle_notification_action(hass, event)),
        )
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_refresh()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    if len(hass.data[DOMAIN]) == 1 and "logger" in hass.data[DOMAIN]:
        for service_name in (
            SERVICE_ADD_MEDICATION,
            SERVICE_LOG_DOSE,
            SERVICE_REFILL_MEDICATION,
            SERVICE_REMOVE_MEDICATION,
        ):
            if hass.services.has_service(DOMAIN, service_name):
                hass.services.async_remove(DOMAIN, service_name)

    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_MEDICATION):
        return

    async def handle_add_medication(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass)
        await runtime_data["manager"].async_add_medication(**call.data)
        await runtime_data["coordinator"].async_request_refresh()
        async_dispatcher_send(hass, SIGNAL_MEDICATIONS_UPDATED)

    async def handle_log_dose(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass)
        taken_at = call.data.get(ATTR_TAKEN_AT)
        if taken_at and dt_util.is_naive(taken_at):
            taken_at = dt_util.as_local(dt_util.as_utc(taken_at))
        await runtime_data["manager"].async_log_dose(call.data[ATTR_MEDICATION_ID], taken_at)
        runtime_data["alert_engine"].dismiss_for_medication(call.data[ATTR_MEDICATION_ID])
        await runtime_data["coordinator"].async_request_refresh()

    async def handle_refill_medication(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass)
        await runtime_data["manager"].async_refill_medication(
            call.data[ATTR_MEDICATION_ID],
            call.data[ATTR_QUANTITY],
        )
        await runtime_data["coordinator"].async_request_refresh()

    async def handle_remove_medication(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass)
        await runtime_data["manager"].async_remove_medication(call.data[ATTR_MEDICATION_ID])
        await runtime_data["coordinator"].async_request_refresh()
        async_dispatcher_send(hass, SIGNAL_MEDICATIONS_UPDATED)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_MEDICATION,
        handle_add_medication,
        schema=ADD_MEDICATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_DOSE,
        handle_log_dose,
        schema=LOG_DOSE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFILL_MEDICATION,
        handle_refill_medication,
        schema=REFILL_MEDICATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_MEDICATION,
        handle_remove_medication,
        schema=REMOVE_MEDICATION_SCHEMA,
    )


def _get_runtime_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return the single runtime payload."""
    entry_ids = [key for key in hass.data[DOMAIN] if key != "logger"]
    return hass.data[DOMAIN][entry_ids[0]]


async def _async_handle_tag_scanned(hass: HomeAssistant, event: Event) -> None:
    """Log a dose when a known NFC tag is scanned."""
    runtime_data = _get_runtime_data(hass)
    tag_id = event.data.get("tag_id")
    if not tag_id:
        return

    medication = runtime_data["manager"].get_by_tag(tag_id)
    if medication is None:
        return

    await runtime_data["manager"].async_log_dose(medication.medication_id)
    runtime_data["alert_engine"].dismiss_for_medication(medication.medication_id)
    await runtime_data["coordinator"].async_request_refresh()
    hass.bus.async_fire(
        EVENT_NFC_LOGGED,
        {
            ATTR_MEDICATION_ID: medication.medication_id,
            ATTR_NFC_TAG_ID: tag_id,
        },
    )


async def _async_handle_notification_action(hass: HomeAssistant, event: Event) -> None:
    """Log a dose from a mobile app notification action."""
    action = event.data.get("action")
    if not isinstance(action, str) or not action.startswith("MEDICATION_CONFIRMED_"):
        return

    medication_id = action.removeprefix("MEDICATION_CONFIRMED_")
    runtime_data = _get_runtime_data(hass)
    if medication_id not in runtime_data["manager"].medications:
        return

    await runtime_data["manager"].async_log_dose(medication_id)
    runtime_data["alert_engine"].dismiss_for_medication(medication_id)
    await runtime_data["coordinator"].async_request_refresh()
