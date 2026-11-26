"""Medication Tracker integration."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, persistent_notification
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .alerts import MedicationAlertEngine
from .const import (
    ACTION_ALL_PREFIX,
    ACTION_CONFIRMED_PREFIX,
    ACTION_SKIP_PREFIX,
    ACTION_SNOOZE_PREFIX,
    ASSET_BASE_URL,
    ATTR_CAREGIVER_NAME,
    ATTR_CAREGIVER_NOTIFY_SERVICE,
    ATTR_CONFIRMATION_REQUIRED,
    ATTR_CONFIRMED_BY,
    ATTR_DATABASE_ENTRY_ID,
    ATTR_DAYS_OF_WEEK,
    ATTR_DOSAGE,
    ATTR_DUPLICATE_GUARD_MINUTES,
    ATTR_FORM,
    ATTR_INSTRUCTIONS,
    ATTR_MAX_REPEATS,
    ATTR_MEDICATION_ID,
    ATTR_MEDICATION_IDS,
    ATTR_MEDICATION_NAME,
    ATTR_MISSED_AFTER_MINUTES,
    ATTR_NFC_TAG_ID,
    ATTR_NOTES,
    ATTR_NOTIFICATION_ENABLED,
    ATTR_NOTIFY_SERVICE,
    ATTR_PROFILE_ID,
    ATTR_PROFILE_NAME,
    ATTR_PURPOSE,
    ATTR_QUANTITY,
    ATTR_REFILL_AT,
    ATTR_REMINDER_MINUTES,
    ATTR_REPEAT_EVERY_MINUTES,
    ATTR_SCHEDULED_TIME,
    ATTR_SCHEDULES,
    ATTR_SOURCE,
    ATTR_TAKEN_AT,
    DEFAULT_MISSED_AFTER_MINUTES,
    DEFAULT_REMINDER_MINUTES,
    DOMAIN,
    EVENT_NFC_LOGGED,
    MEDICATION_BINARY_SENSOR_UNIQUE_KEYS,
    MEDICATION_BUTTON_UNIQUE_KEYS,
    MEDICATION_SENSOR_UNIQUE_KEYS,
    PANEL_COMPONENT,
    PANEL_URL_PATH,
    PLATFORMS,
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
    VERSION,
)
from .coordinator import MedicationTrackerCoordinator
from .intent import async_register_intents
from .manager import MedicationTrackerManager
from .runtime import (
    async_refresh,
    async_skip,
    async_context_user_name,
    async_snooze,
    async_take,
    async_take_all,
    async_undo_last,
    get_runtime,
)
from .websocket_api import async_register_commands

LOGGER = logging.getLogger(__name__)

CARD_PATH = f"{ASSET_BASE_URL}/medication-tracker-card.js"
CARD_PATH_V2 = f"{ASSET_BASE_URL}/medication-tracker-cards-v2.js"
CARD_PATH_V3 = f"{ASSET_BASE_URL}/medication-tracker-cards-v3.js"
PANEL_JS_PATH = f"{ASSET_BASE_URL}/medication-tracker-panel.js"
TODAY_CARD_PATH = f"{ASSET_BASE_URL}/medication-tracker-today-card.js"

SERVICE_ADD_MEDICATION = "add_medication"
SERVICE_LOG_DOSE = "log_dose"
SERVICE_LOG_ALL_DUE = "log_all_due"
SERVICE_DELETE_DOSE = "delete_dose"
SERVICE_REFILL_MEDICATION = "refill_medication"
SERVICE_REMOVE_MEDICATION = "remove_medication"
SERVICE_RESET_HISTORY = "reset_history"
SERVICE_SKIP_MEDICATION = "skip_medication"
SERVICE_SNOOZE_MEDICATION = "snooze_medication"
SERVICE_UPDATE_SETTINGS = "update_settings"
SERVICE_UNDO_LAST_DOSE = "undo_last_dose"
SERVICE_NAMES = (
    SERVICE_ADD_MEDICATION,
    SERVICE_LOG_DOSE,
    SERVICE_LOG_ALL_DUE,
    SERVICE_DELETE_DOSE,
    SERVICE_REFILL_MEDICATION,
    SERVICE_REMOVE_MEDICATION,
    SERVICE_RESET_HISTORY,
    SERVICE_SKIP_MEDICATION,
    SERVICE_SNOOZE_MEDICATION,
    SERVICE_UPDATE_SETTINGS,
    SERVICE_UNDO_LAST_DOSE,
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
        vol.Required(ATTR_SCHEDULES): [cv.string],
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
        vol.Optional(ATTR_REPEAT_EVERY_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
        vol.Optional(ATTR_MAX_REPEATS): vol.All(vol.Coerce(int), vol.Range(min=0, max=20)),
        vol.Optional(ATTR_DAYS_OF_WEEK): vol.All(
            cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))]
        ),
        vol.Optional("end_date"): cv.string,
        vol.Optional("as_needed"): cv.boolean,
        vol.Optional("max_doses_per_day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=48)),
        vol.Optional("interval_days"): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
        vol.Optional("anchor_date"): cv.string,
        vol.Optional("escalate_after_minutes"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
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

LOG_ALL_DUE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_PROFILE_ID): cv.string,
        vol.Optional(ATTR_MEDICATION_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_SOURCE, default="manual"): cv.string,
        vol.Optional(ATTR_CONFIRMED_BY): cv.string,
    }
)

DELETE_DOSE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Required(ATTR_TAKEN_AT): cv.string,
    }
)

REFILL_MEDICATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MEDICATION_ID): cv.string,
        vol.Required(ATTR_QUANTITY): vol.Coerce(float),
    }
)

REMOVE_MEDICATION_SCHEMA = vol.Schema({vol.Required(ATTR_MEDICATION_ID): cv.string})
RESET_HISTORY_SCHEMA = vol.Schema({vol.Required(ATTR_MEDICATION_ID): cv.string})
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
UNDO_LAST_DOSE_SCHEMA = vol.Schema({vol.Required(ATTR_MEDICATION_ID): cv.string})
UPDATE_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional(SETTING_ESCALATION_NOTIFY): vol.Any(None, cv.string),
        vol.Optional(SETTING_CRITICAL): cv.boolean,
        vol.Optional(SETTING_ANNOUNCE_SERVICE): vol.Any(None, cv.string),
        vol.Optional(SETTING_ANNOUNCE_HOME_ENTITY): vol.Any(None, cv.string),
        vol.Optional(SETTING_QUIET_START): vol.Any(None, cv.string),
        vol.Optional(SETTING_QUIET_END): vol.Any(None, cv.string),
        vol.Optional(SETTING_DEFAULT_NOTIFY): vol.Any(None, cv.string),
        vol.Optional(SETTING_FALLBACK_NOTIFY): vol.Any(None, cv.string),
        vol.Optional(SETTING_ALL_TAG_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(SETTING_PROFILE_TAGS): {cv.string: cv.string},
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration domain."""
    hass.data.setdefault(DOMAIN, {"logger": LOGGER})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Medication Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {"logger": LOGGER})
    await _async_register_frontend(hass)
    await _async_sync_custom_sentences(hass)
    manager = MedicationTrackerManager(hass)
    await manager.async_initialize()

    alert_engine = MedicationAlertEngine(hass, manager)
    coordinator = MedicationTrackerCoordinator(hass, manager, alert_engine)
    hass.data[DOMAIN][entry.entry_id] = {
        "manager": manager,
        "coordinator": coordinator,
        "alert_engine": alert_engine,
    }
    _async_prune_orphaned_registry_entries(hass, entry, set(manager.medications))

    await async_register_intents(hass)
    await _async_register_services(hass)
    async_register_websocket_api(hass)
    await _async_register_panel(hass)
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
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _async_remove_panel(hass)
        if not any(isinstance(value, dict) and "manager" in value for value in hass.data[DOMAIN].values()):
            for service_name in SERVICE_NAMES:
                if hass.services.has_service(DOMAIN, service_name):
                    hass.services.async_remove(DOMAIN, service_name)

    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_MEDICATION):
        return

    async def handle_add_medication(call: ServiceCall) -> None:
        runtime = get_runtime(hass)
        await runtime["manager"].async_add_medication(**call.data)
        await async_refresh(hass)

    async def handle_log_dose(call: ServiceCall) -> None:
        taken_at = call.data.get(ATTR_TAKEN_AT)
        if taken_at and _is_naive_datetime(taken_at):
            taken_at = dt_util.as_local(dt_util.as_utc(taken_at))
        await async_take(
            hass,
            call.data[ATTR_MEDICATION_ID],
            taken_at=taken_at,
            source=call.data.get(ATTR_SOURCE, "manual"),
            confirmed_by=call.data.get(ATTR_CONFIRMED_BY),
            allow_duplicate=call.data.get("allow_duplicate", False),
            taken_by=await async_context_user_name(hass, call.context),
        )

    async def handle_log_all_due(call: ServiceCall) -> None:
        await async_take_all(
            hass,
            profile_id=call.data.get(ATTR_PROFILE_ID),
            medication_ids=call.data.get(ATTR_MEDICATION_IDS),
            source=call.data.get(ATTR_SOURCE, "manual"),
            confirmed_by=call.data.get(ATTR_CONFIRMED_BY),
            taken_by=await async_context_user_name(hass, call.context),
        )

    async def handle_undo_last_dose(call: ServiceCall) -> None:
        await async_undo_last(hass, call.data[ATTR_MEDICATION_ID])

    async def handle_delete_dose(call: ServiceCall) -> None:
        runtime = get_runtime(hass)
        await runtime["manager"].async_delete_dose(call.data[ATTR_MEDICATION_ID], call.data[ATTR_TAKEN_AT])
        await async_refresh(hass)

    async def handle_refill_medication(call: ServiceCall) -> None:
        runtime = get_runtime(hass)
        await runtime["manager"].async_refill_medication(
            call.data[ATTR_MEDICATION_ID],
            call.data[ATTR_QUANTITY],
        )
        await async_refresh(hass)

    async def handle_remove_medication(call: ServiceCall) -> None:
        runtime = get_runtime(hass)
        medication_id = call.data[ATTR_MEDICATION_ID]
        await runtime["manager"].async_remove_medication(medication_id)
        await runtime["alert_engine"].async_dismiss_for_medications([medication_id])
        _async_remove_medication_registry_entries(hass, medication_id)
        await async_refresh(hass)

    async def handle_reset_history(call: ServiceCall) -> None:
        runtime = get_runtime(hass)
        await runtime["manager"].async_reset_history(call.data[ATTR_MEDICATION_ID])
        await async_refresh(hass)

    async def handle_snooze_medication(call: ServiceCall) -> None:
        await async_snooze(hass, call.data[ATTR_MEDICATION_ID], call.data["minutes"])

    async def handle_skip_medication(call: ServiceCall) -> None:
        scheduled_time = call.data.get(ATTR_SCHEDULED_TIME)
        if scheduled_time and _is_naive_datetime(scheduled_time):
            scheduled_time = dt_util.as_local(dt_util.as_utc(scheduled_time))
        await async_skip(hass, call.data[ATTR_MEDICATION_ID], scheduled_time)

    async def handle_update_settings(call: ServiceCall) -> None:
        runtime = get_runtime(hass)
        await runtime["manager"].async_update_settings(dict(call.data))
        await async_refresh(hass)

    for name, handler, schema in (
        (SERVICE_ADD_MEDICATION, handle_add_medication, ADD_MEDICATION_SCHEMA),
        (SERVICE_LOG_DOSE, handle_log_dose, LOG_DOSE_SCHEMA),
        (SERVICE_LOG_ALL_DUE, handle_log_all_due, LOG_ALL_DUE_SCHEMA),
        (SERVICE_DELETE_DOSE, handle_delete_dose, DELETE_DOSE_SCHEMA),
        (SERVICE_REFILL_MEDICATION, handle_refill_medication, REFILL_MEDICATION_SCHEMA),
        (SERVICE_REMOVE_MEDICATION, handle_remove_medication, REMOVE_MEDICATION_SCHEMA),
        (SERVICE_RESET_HISTORY, handle_reset_history, RESET_HISTORY_SCHEMA),
        (SERVICE_SNOOZE_MEDICATION, handle_snooze_medication, SNOOZE_MEDICATION_SCHEMA),
        (SERVICE_SKIP_MEDICATION, handle_skip_medication, SKIP_MEDICATION_SCHEMA),
        (SERVICE_UPDATE_SETTINGS, handle_update_settings, UPDATE_SETTINGS_SCHEMA),
        (SERVICE_UNDO_LAST_DOSE, handle_undo_last_dose, UNDO_LAST_DOSE_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=schema)


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register websocket commands once (they cannot be unregistered)."""
    if hass.data[DOMAIN].get("websocket_registered"):
        return
    async_register_commands(hass)
    hass.data[DOMAIN]["websocket_registered"] = True


def _is_naive_datetime(value: datetime) -> bool:
    """Return whether a datetime has no usable timezone info."""
    return value.tzinfo is None or value.tzinfo.utcoffset(value) is None


def _sync_copy_sentences(source_path: Path, target_path: Path) -> None:
    """Copy the packaged Assist sentences (runs in the executor)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source_content = source_path.read_text(encoding="utf-8")
    if target_path.exists() and target_path.read_text(encoding="utf-8") == source_content:
        return
    target_path.write_text(source_content, encoding="utf-8")


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register the Lovelace card and panel assets once."""
    if hass.data[DOMAIN].get("frontend_registered"):
        return

    frontend_dir = Path(__file__).parent / "frontend"
    card_file = frontend_dir / "medication-tracker-card.js"
    panel_file = frontend_dir / "medication-tracker-panel.js"
    today_card_file = frontend_dir / "medication-tracker-today-card.js"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(CARD_PATH, str(card_file), cache_headers=False),
            StaticPathConfig(CARD_PATH_V2, str(card_file), cache_headers=False),
            # Existing dashboards reference the v3 filename.
            StaticPathConfig(CARD_PATH_V3, str(card_file), cache_headers=False),
            StaticPathConfig(PANEL_JS_PATH, str(panel_file), cache_headers=False),
            StaticPathConfig(TODAY_CARD_PATH, str(today_card_file), cache_headers=False),
        ]
    )
    add_extra_js_url(hass, f"{CARD_PATH_V3}?v={VERSION}")
    add_extra_js_url(hass, f"{TODAY_CARD_PATH}?v={VERSION}")
    hass.data[DOMAIN]["frontend_registered"] = True


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Add the Medications sidebar panel."""
    if hass.data[DOMAIN].get("panel_registered"):
        return
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT,
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{PANEL_JS_PATH}?v={VERSION}",
        sidebar_title="Medications",
        sidebar_icon="mdi:pill",
        require_admin=False,
        config={},
    )
    hass.data[DOMAIN]["panel_registered"] = True


def _async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel."""
    if hass.data[DOMAIN].pop("panel_registered", False):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)


async def _async_sync_custom_sentences(hass: HomeAssistant) -> None:
    """Copy packaged Assist sentences into Home Assistant custom_sentences."""
    source_path = Path(__file__).parent / "sentences" / "en" / "medication_tracker.yaml"
    target_path = Path(hass.config.path("custom_sentences", "en", "medication_tracker.yaml"))
    try:
        await hass.async_add_executor_job(_sync_copy_sentences, source_path, target_path)
    except OSError as err:
        LOGGER.warning("Could not install Assist sentences: %s", err)


async def _async_handle_tag_scanned(hass: HomeAssistant, event: Event) -> None:
    """Handle an NFC tag: one medication, everything due, or one person's medications."""
    tag_id = event.data.get("tag_id")
    if not tag_id:
        return
    try:
        runtime = get_runtime(hass)
        manager = runtime["manager"]
        target = manager.resolve_tag(tag_id)
        if target is None:
            return
        kind, value = target
        who = await async_context_user_name(hass, event.context)
        if kind == "medication":
            await async_take(hass, value.medication_id, source="nfc", taken_by=who)
            medication_ids = [value.medication_id]
        else:
            result = await async_take_all(
                hass,
                profile_id=value if kind == "profile" else None,
                source="nfc",
                taken_by=who,
            )
            medication_ids = result["logged"]
            if not medication_ids:
                persistent_notification.async_create(
                    hass,
                    "Nothing is due right now, so no doses were logged.",
                    title="Medication Tracker",
                    notification_id=f"{DOMAIN}_nothing_due",
                )
                return
        hass.bus.async_fire(
            EVENT_NFC_LOGGED,
            {
                ATTR_MEDICATION_ID: medication_ids[0],
                ATTR_MEDICATION_IDS: medication_ids,
                ATTR_NFC_TAG_ID: tag_id,
            },
        )
    except HomeAssistantError as err:
        LOGGER.warning("NFC tag %s could not be processed: %s", tag_id, err)
        persistent_notification.async_create(
            hass,
            f"Tag scan not logged: {err}",
            title="Medication Tracker",
            notification_id=f"{DOMAIN}_tag_error",
        )


async def _async_handle_notification_action(hass: HomeAssistant, event: Event) -> None:
    """Handle the buttons on a mobile app notification."""
    action = event.data.get("action")
    if not isinstance(action, str) or not action.startswith("MEDICATION_"):
        return
    try:
        manager = get_runtime(hass)["manager"]
        who = await async_context_user_name(hass, event.context)
        if action.startswith(ACTION_CONFIRMED_PREFIX):
            medication_id = action.removeprefix(ACTION_CONFIRMED_PREFIX)
            if medication_id in manager.medications:
                await async_take(hass, medication_id, source="mobile_action", taken_by=who)
        elif action.startswith(ACTION_ALL_PREFIX):
            profile_id = action.removeprefix(ACTION_ALL_PREFIX)
            await async_take_all(hass, profile_id=profile_id, source="mobile_action", taken_by=who)
        elif action.startswith(ACTION_SNOOZE_PREFIX):
            medication_id = action.removeprefix(ACTION_SNOOZE_PREFIX)
            if medication_id in manager.medications:
                await async_snooze(hass, medication_id, 10)
        elif action.startswith(ACTION_SKIP_PREFIX):
            medication_id = action.removeprefix(ACTION_SKIP_PREFIX)
            if medication_id in manager.medications:
                await async_skip(hass, medication_id)
    except HomeAssistantError as err:
        LOGGER.warning("Notification action %s failed: %s", action, err)


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


def _async_prune_orphaned_registry_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    valid_medication_ids: set[str],
) -> None:
    """Remove stale entity and device registry entries for deleted medications."""
    entity_registry = er.async_get(hass)

    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity_entry.domain not in {"sensor", "binary_sensor", "button"}:
            continue
        medication_id = _get_medication_id_from_unique_id(entity_entry.unique_id)
        if medication_id is None or medication_id in valid_medication_ids:
            continue
        entity_registry.async_remove(entity_entry.entity_id)

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        medication_ids = {
            identifier[1]
            for identifier in device.identifiers
            if len(identifier) >= 2 and identifier[0] == DOMAIN and identifier[1] != "summary"
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
