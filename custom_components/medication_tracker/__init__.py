"""Medication Tracker integration."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .alerts import MedicationAlertEngine
from .const import (
    ATTR_CAREGIVER_NAME,
    ATTR_CAREGIVER_NOTIFY_SERVICE,
    ATTR_CONFIRMATION_REQUIRED,
    ATTR_CONFIRMED_BY,
    ATTR_DUPLICATE_GUARD_MINUTES,
    ATTR_MEDICATION_ID,
    ATTR_MISSED_AFTER_MINUTES,
    ATTR_NOTIFICATION_ENABLED,
    ATTR_NOTIFY_SERVICE,
    ATTR_NFC_TAG_ID,
    ATTR_PROFILE_ID,
    ATTR_PROFILE_NAME,
    ATTR_PURPOSE,
    ATTR_QUANTITY,
    ATTR_REFILL_AT,
    ATTR_REMINDER_MINUTES,
    ATTR_SCHEDULED_TIME,
    ATTR_SCHEDULES,
    ATTR_SOURCE,
    ATTR_TAKEN_AT,
    ATTR_DATABASE_ENTRY_ID,
    ATTR_FORM,
    ATTR_INSTRUCTIONS,
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
CARD_PATH = "/medication_tracker_assets/medication-tracker-card.js"
CARD_PATH_V2 = "/medication_tracker_assets/medication-tracker-cards-v2.js"

SERVICE_ADD_MEDICATION = "add_medication"
SERVICE_LOG_DOSE = "log_dose"
SERVICE_REFILL_MEDICATION = "refill_medication"
SERVICE_REMOVE_MEDICATION = "remove_medication"
SERVICE_SKIP_MEDICATION = "skip_medication"
SERVICE_SNOOZE_MEDICATION = "snooze_medication"

MEDICATION_SENSOR_UNIQUE_KEYS = (
    "belongs_to",
    "next_dose",
    "last_taken",
    "missed_doses",
    "days_remaining",
    "compliance_percentage",
    "snoozed_until",
    "stock_depletion_date",
)
MEDICATION_BINARY_SENSOR_UNIQUE_KEYS = (
    "due_now",
    "needs_refill",
    "has_missed_dose",
    "caregiver_confirmation_needed",
)
MEDICATION_BUTTON_UNIQUE_KEYS = (
    "log_dose",
    "skip_dose",
    "snooze_10_minutes",
    "test_due_notification",
    "test_missed_notification",
    "test_refill_notification",
    "test_caregiver_notification",
)
MEDICATION_ENTITY_SUFFIXES = tuple(
    sorted(
        {
            *MEDICATION_SENSOR_UNIQUE_KEYS,
            *MEDICATION_BINARY_SENSOR_UNIQUE_KEYS,
            *MEDICATION_BUTTON_UNIQUE_KEYS,
        },
        key=len,
        reverse=True,
    )
)

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
        vol.Optional(ATTR_INSTRUCTIONS, default=""): cv.string,
        vol.Optional(ATTR_PURPOSE, default=""): cv.string,
        vol.Optional(ATTR_FORM, default=""): cv.string,
        vol.Optional(ATTR_DATABASE_ENTRY_ID): cv.string,
        vol.Optional(ATTR_NFC_TAG_ID): cv.string,
        vol.Optional(ATTR_NOTIFICATION_ENABLED, default=True): cv.boolean,
        vol.Optional(ATTR_NOTIFY_SERVICE): cv.string,
        vol.Optional(ATTR_CAREGIVER_NAME): cv.string,
        vol.Optional(ATTR_CAREGIVER_NOTIFY_SERVICE): cv.string,
        vol.Optional(ATTR_CONFIRMATION_REQUIRED, default=False): cv.boolean,
        vol.Optional(ATTR_REMINDER_MINUTES, default=DEFAULT_REMINDER_MINUTES): vol.Coerce(int),
        vol.Optional(ATTR_MISSED_AFTER_MINUTES, default=DEFAULT_MISSED_AFTER_MINUTES): vol.Coerce(int),
        vol.Optional(ATTR_DUPLICATE_GUARD_MINUTES, default=0): vol.Coerce(int),
    }
)

LOG_DOSE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Optional(ATTR_TAKEN_AT): cv.datetime,
        vol.Optional(ATTR_SOURCE, default="manual"): cv.string,
        vol.Optional(ATTR_CONFIRMED_BY): cv.string,
        vol.Optional("allow_duplicate", default=False): cv.boolean,
    }
)

REFILL_MEDICATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Required(ATTR_QUANTITY): vol.Coerce(float),
    }
)

REMOVE_MEDICATION_SCHEMA = vol.Schema({vol.Required(ATTR_MEDICATION_ID): cv.string})
SNOOZE_MEDICATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
    }
)
SKIP_MEDICATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Optional(ATTR_SCHEDULED_TIME): cv.datetime,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration domain."""
    hass.data.setdefault(DOMAIN, {"logger": LOGGER})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Medication Tracker from a config entry."""
    await _async_register_frontend(hass)
    manager = MedicationTrackerManager(hass)
    await manager.async_initialize()

    alert_engine = MedicationAlertEngine(hass, manager)
    coordinator = MedicationTrackerCoordinator(hass, manager, alert_engine)
    hass.data[DOMAIN][entry.entry_id] = {
        "manager": manager,
        "coordinator": coordinator,
        "alert_engine": alert_engine,
    }
    _async_prune_orphaned_registry_entries(hass, set(manager.medications))

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
            SERVICE_SKIP_MEDICATION,
            SERVICE_SNOOZE_MEDICATION,
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
        if taken_at and _is_naive_datetime(taken_at):
            taken_at = dt_util.as_local(dt_util.as_utc(taken_at))
        await runtime_data["manager"].async_log_dose(
            call.data[ATTR_MEDICATION_ID],
            taken_at,
            source=call.data.get(ATTR_SOURCE, "manual"),
            confirmed_by=call.data.get(ATTR_CONFIRMED_BY),
            allow_duplicate=call.data.get("allow_duplicate", False),
        )
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
        medication_id = call.data[ATTR_MEDICATION_ID]
        await runtime_data["manager"].async_remove_medication(medication_id)
        _async_remove_medication_registry_entries(hass, medication_id)
        await runtime_data["coordinator"].async_request_refresh()
        async_dispatcher_send(hass, SIGNAL_MEDICATIONS_UPDATED)

    async def handle_snooze_medication(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass)
        await runtime_data["manager"].async_snooze_medication(
            call.data[ATTR_MEDICATION_ID],
            call.data["minutes"],
        )
        runtime_data["alert_engine"].dismiss_for_medication(call.data[ATTR_MEDICATION_ID])
        await runtime_data["coordinator"].async_request_refresh()

    async def handle_skip_medication(call: ServiceCall) -> None:
        runtime_data = _get_runtime_data(hass)
        scheduled_time = call.data.get(ATTR_SCHEDULED_TIME)
        if scheduled_time and _is_naive_datetime(scheduled_time):
            scheduled_time = dt_util.as_local(dt_util.as_utc(scheduled_time))
        await runtime_data["manager"].async_skip_medication_occurrence(
            call.data[ATTR_MEDICATION_ID],
            scheduled_time,
        )
        runtime_data["alert_engine"].dismiss_for_medication(call.data[ATTR_MEDICATION_ID])
        await runtime_data["coordinator"].async_request_refresh()

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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SNOOZE_MEDICATION,
        handle_snooze_medication,
        schema=SNOOZE_MEDICATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SKIP_MEDICATION,
        handle_skip_medication,
        schema=SKIP_MEDICATION_SCHEMA,
    )


def _get_runtime_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return the single runtime payload."""
    entry_ids = [key for key in hass.data[DOMAIN] if key != "logger"]
    return hass.data[DOMAIN][entry_ids[0]]


def _is_naive_datetime(value: datetime) -> bool:
    """Return whether a datetime has no usable timezone info."""
    return value.tzinfo is None or value.tzinfo.utcoffset(value) is None


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register the custom Lovelace card asset once."""
    if hass.data[DOMAIN].get("frontend_registered"):
        return

    asset_path = Path(__file__).parent / "frontend" / "medication-tracker-card.js"
    cache_buster = int(asset_path.stat().st_mtime)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(CARD_PATH, str(asset_path), cache_headers=False),
            StaticPathConfig(CARD_PATH_V2, str(asset_path), cache_headers=False),
        ]
    )
    add_extra_js_url(hass, f"{CARD_PATH_V2}?v={cache_buster}")
    hass.data[DOMAIN]["frontend_registered"] = True


async def _async_handle_tag_scanned(hass: HomeAssistant, event: Event) -> None:
    """Log a dose when a known NFC tag is scanned."""
    runtime_data = _get_runtime_data(hass)
    tag_id = event.data.get("tag_id")
    if not tag_id:
        return

    medication = runtime_data["manager"].get_by_tag(tag_id)
    if medication is None:
        return

    await runtime_data["manager"].async_log_dose(medication.medication_id, source="nfc")
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

    await runtime_data["manager"].async_log_dose(medication_id, source="mobile_action")
    runtime_data["alert_engine"].dismiss_for_medication(medication_id)
    await runtime_data["coordinator"].async_request_refresh()


def _async_remove_medication_registry_entries(hass: HomeAssistant, medication_id: str) -> None:
    """Remove entity and device registry entries for a deleted medication."""
    entity_registry = er.async_get(hass)

    for platform_domain, unique_keys in (
        ("sensor", MEDICATION_SENSOR_UNIQUE_KEYS),
        ("binary_sensor", MEDICATION_BINARY_SENSOR_UNIQUE_KEYS),
        ("button", MEDICATION_BUTTON_UNIQUE_KEYS),
    ):
        for unique_key in unique_keys:
            entity_id = entity_registry.async_get_entity_id(
                platform_domain,
                DOMAIN,
                f"{medication_id}_{unique_key}",
            )
            if entity_id:
                entity_registry.async_remove(entity_id)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, medication_id)})
    if device:
        device_registry.async_remove_device(device.id)


def _async_prune_orphaned_registry_entries(hass: HomeAssistant, valid_medication_ids: set[str]) -> None:
    """Remove stale entity and device registry entries for deleted medications."""
    entity_registry = er.async_get(hass)

    for entry in list(entity_registry.entities.values()):
        if entry.platform != DOMAIN or entry.domain not in {"sensor", "binary_sensor", "button"}:
            continue

        medication_id = _get_medication_id_from_unique_id(entry.unique_id)
        if medication_id is None or medication_id in valid_medication_ids:
            continue

        entity_registry.async_remove(entry.entity_id)

    device_registry = dr.async_get(hass)
    for device in list(device_registry.devices.values()):
        medication_ids = {
            identifier_value
            for identifier_domain, identifier_value in device.identifiers
            if identifier_domain == DOMAIN and identifier_value != "summary"
        }
        if medication_ids and medication_ids.isdisjoint(valid_medication_ids):
            device_registry.async_remove_device(device.id)


def _get_medication_id_from_unique_id(unique_id: str) -> str | None:
    """Extract a medication ID from a unique ID when it belongs to a medication entity."""
    for suffix in MEDICATION_ENTITY_SUFFIXES:
        marker = f"_{suffix}"
        if unique_id.endswith(marker):
            return unique_id.removesuffix(marker)
    return None
