"""Websocket API used by the Medication Tracker panel."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    DEFAULT_MAX_REPEATS,
    DEFAULT_MISSED_AFTER_MINUTES,
    DEFAULT_REMINDER_MINUTES,
    DEFAULT_REPEAT_EVERY_MINUTES,
    DOMAIN,
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
from .runtime import (
    async_refresh,
    async_skip,
    async_snooze,
    async_take,
    async_take_all,
    async_undo_last,
    get_runtime,
)

PREFIX = f"{DOMAIN}/"


def _handler(func):
    """Wrap a command so errors become websocket errors instead of crashes."""

    async def wrapper(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
        try:
            result = await func(hass, connection, msg)
        except HomeAssistantError as err:
            connection.send_error(msg["id"], "failed", str(err))
            return
        connection.send_result(msg["id"], result)

    wrapper.__name__ = func.__name__
    return wrapper


def _notify_services(hass: HomeAssistant) -> list[str]:
    """List the notify services that look like phones first."""
    names = sorted(f"notify.{name}" for name in hass.services.async_services().get("notify", {}))
    return sorted(names, key=lambda item: (not item.startswith("notify.mobile_app_"), item))


def _build_state(hass: HomeAssistant) -> dict[str, Any]:
    manager = get_runtime(hass)["manager"]
    medications = [manager.get_snapshot(med.medication_id) for med in manager.list_medications()]
    medications.sort(key=lambda item: (item["profile_name"].lower(), item["medication_name"].lower()))
    return {
        "version": VERSION,
        "medications": medications,
        "profiles": manager.list_profiles(),
        "today": manager.get_today_doses(),
        "as_needed": manager.get_as_needed(),
        "recent_logs": manager.get_recent_logs(60),
        "settings": manager.settings,
        "summary": manager.get_summary(),
        "notify_services": _notify_services(hass),
        "database": [
            {"id": entry.get("id"), "name": entry.get("name"), "form": entry.get("form"), "purpose": entry.get("purpose")}
            for entry in manager.list_database_entries()
        ],
    }


@websocket_api.websocket_command({vol.Required("type"): PREFIX + "get_state"})
@websocket_api.async_response
@_handler
async def ws_get_state(hass, connection, msg):
    """Return everything the panel needs in one call."""
    return _build_state(hass)


def _parse_taken_at(value: str | None) -> datetime | None:
    """Parse a user-supplied dose time, rejecting the future and very old times."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise HomeAssistantError("That time is not valid.") from err
    parsed = dt_util.as_local(parsed)
    now = dt_util.now()
    if parsed > now + timedelta(minutes=1):
        raise HomeAssistantError("A dose cannot be logged in the future.")
    if parsed < now - timedelta(days=7):
        raise HomeAssistantError("That is too long ago to log from here.")
    return parsed


def _user_name(connection) -> str | None:
    return connection.user.name if connection.user else None


@websocket_api.websocket_command(
    {
        vol.Required("type"): PREFIX + "take",
        vol.Required("medication_id"): str,
        vol.Optional("taken_at"): vol.Any(None, str),
    }
)
@websocket_api.async_response
@_handler
async def ws_take(hass, connection, msg):
    """Mark one medication as taken, optionally at an earlier time."""
    await async_take(
        hass,
        msg["medication_id"],
        source="panel",
        taken_at=_parse_taken_at(msg.get("taken_at")),
        taken_by=_user_name(connection),
    )
    return {"ok": True}


@websocket_api.websocket_command(
    {vol.Required("type"): PREFIX + "undo_last", vol.Required("medication_id"): str}
)
@websocket_api.async_response
@_handler
async def ws_undo_last(hass, connection, msg):
    """Undo the most recent dose of a medication."""
    await async_undo_last(hass, msg["medication_id"])
    return {"ok": True}


@websocket_api.websocket_command(
    {vol.Required("type"): PREFIX + "get_history", vol.Optional("days", default=90): vol.All(int, vol.Range(min=1, max=730))}
)
@websocket_api.async_response
@_handler
async def ws_get_history(hass, connection, msg):
    """Return the dose log for the last N days (used for CSV export)."""
    return {"logs": get_runtime(hass)["manager"].get_recent_logs(limit=20000, days=msg["days"])}


@websocket_api.websocket_command(
    {vol.Required("type"): PREFIX + "take_all", vol.Optional("profile_id"): vol.Any(None, str)}
)
@websocket_api.async_response
@_handler
async def ws_take_all(hass, connection, msg):
    """Mark everything that is due as taken."""
    return await async_take_all(
        hass, profile_id=msg.get("profile_id"), source="panel", taken_by=_user_name(connection)
    )


@websocket_api.websocket_command(
    {vol.Required("type"): PREFIX + "skip", vol.Required("medication_id"): str}
)
@websocket_api.async_response
@_handler
async def ws_skip(hass, connection, msg):
    """Skip the current dose."""
    await async_skip(hass, msg["medication_id"])
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): PREFIX + "snooze",
        vol.Required("medication_id"): str,
        vol.Optional("minutes", default=10): vol.All(int, vol.Range(min=1, max=1440)),
    }
)
@websocket_api.async_response
@_handler
async def ws_snooze(hass, connection, msg):
    """Snooze reminders."""
    await async_snooze(hass, msg["medication_id"], msg["minutes"])
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): PREFIX + "refill",
        vol.Required("medication_id"): str,
        vol.Required("quantity"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)
@websocket_api.async_response
@_handler
async def ws_refill(hass, connection, msg):
    """Add stock."""
    await get_runtime(hass)["manager"].async_refill_medication(msg["medication_id"], msg["quantity"])
    await async_refresh(hass)
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): PREFIX + "save_medication",
        vol.Optional("medication_id"): vol.Any(None, str),
        vol.Required("profile_name"): vol.All(str, vol.Length(min=1)),
        vol.Optional("profile_id"): vol.Any(None, str),
        vol.Required("medication_name"): vol.All(str, vol.Length(min=1)),
        vol.Required("dosage"): str,
        vol.Required("schedules"): [str],
        vol.Optional("days_of_week"): vol.Any(None, [vol.All(int, vol.Range(min=0, max=6))]),
        vol.Optional("quantity"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("refill_at"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("notes", default=""): str,
        vol.Optional("instructions", default=""): str,
        vol.Optional("purpose", default=""): str,
        vol.Optional("form", default=""): str,
        vol.Optional("nfc_tag_id"): vol.Any(None, str),
        vol.Optional("notification_enabled", default=True): bool,
        vol.Optional("notify_service"): vol.Any(None, str),
        vol.Optional("caregiver_name"): vol.Any(None, str),
        vol.Optional("caregiver_notify_service"): vol.Any(None, str),
        vol.Optional("confirmation_required", default=False): bool,
        vol.Optional("reminder_minutes", default=DEFAULT_REMINDER_MINUTES): vol.All(int, vol.Range(min=1, max=720)),
        vol.Optional("missed_after_minutes", default=DEFAULT_MISSED_AFTER_MINUTES): vol.All(int, vol.Range(min=1, max=1440)),
        vol.Optional("duplicate_guard_minutes", default=0): vol.All(int, vol.Range(min=0, max=1440)),
        vol.Optional("repeat_every_minutes", default=DEFAULT_REPEAT_EVERY_MINUTES): vol.All(int, vol.Range(min=0, max=240)),
        vol.Optional("max_repeats", default=DEFAULT_MAX_REPEATS): vol.All(int, vol.Range(min=0, max=20)),
        vol.Optional("database_entry_id"): vol.Any(None, str),
        vol.Optional("end_date"): vol.Any(None, str),
        vol.Optional("as_needed", default=False): bool,
        vol.Optional("max_doses_per_day"): vol.Any(None, vol.All(int, vol.Range(min=0, max=48))),
        vol.Optional("interval_days", default=1): vol.All(int, vol.Range(min=1, max=30)),
        vol.Optional("anchor_date"): vol.Any(None, str),
        vol.Optional("escalate_after_minutes", default=0): vol.All(int, vol.Range(min=0, max=1440)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_save_medication(hass, connection, msg):
    """Create or edit a medication."""
    manager = get_runtime(hass)["manager"]
    data = {key: value for key, value in msg.items() if key not in ("id", "type")}

    existing_id = data.pop("medication_id", None)
    profile_name = data.pop("profile_name").strip()
    profile_id = data.pop("profile_id", None)
    if not profile_id:
        # Reuse the profile id when this person already exists.
        for pid, name in manager.list_profiles().items():
            if name.casefold() == profile_name.casefold():
                profile_id = pid
                break
        else:
            profile_id = slugify(profile_name)

    if existing_id:
        if existing_id not in manager.medications:
            raise HomeAssistantError(f"Unknown medication: {existing_id}")
        medication_id = existing_id
    else:
        base = slugify(f"{profile_name}_{data['medication_name']}")
        medication_id, counter = base, 2
        while medication_id in manager.medications:
            medication_id = f"{base}_{counter}"
            counter += 1

    # Optional nullable fields: an explicit null clears them.
    for key in ("quantity", "refill_at"):
        data.setdefault(key, None)
    # The panel always sends the whole form, so an empty value means "clear it".
    data["end_date"] = data.get("end_date") or ""
    data["max_doses_per_day"] = data.get("max_doses_per_day") or 0
    if not data.get("anchor_date"):
        data.pop("anchor_date", None)
    for key in ("caregiver_name", "caregiver_notify_service"):
        if key in data and data[key] is None:
            data[key] = ""

    medication = await manager.async_add_medication(
        profile_id=profile_id,
        profile_name=profile_name,
        medication_id=medication_id,
        **data,
    )
    await async_refresh(hass)
    return {"medication_id": medication.medication_id}


@websocket_api.websocket_command(
    {vol.Required("type"): PREFIX + "delete_medication", vol.Required("medication_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_delete_medication(hass, connection, msg):
    """Remove a medication."""
    from . import _async_remove_medication_registry_entries

    runtime = get_runtime(hass)
    await runtime["manager"].async_remove_medication(msg["medication_id"])
    await runtime["alert_engine"].async_dismiss_for_medications([msg["medication_id"]])
    _async_remove_medication_registry_entries(hass, msg["medication_id"])
    await async_refresh(hass)
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): PREFIX + "delete_dose",
        vol.Required("medication_id"): str,
        vol.Required("taken_at"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_delete_dose(hass, connection, msg):
    """Delete a logged dose."""
    await get_runtime(hass)["manager"].async_delete_dose(msg["medication_id"], msg["taken_at"])
    await async_refresh(hass)
    return {"ok": True}


@websocket_api.websocket_command(
    {vol.Required("type"): PREFIX + "reset_history", vol.Required("medication_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_reset_history(hass, connection, msg):
    """Clear the missed-dose history."""
    await get_runtime(hass)["manager"].async_reset_history(msg["medication_id"])
    await async_refresh(hass)
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): PREFIX + "save_settings",
        vol.Optional(SETTING_DEFAULT_NOTIFY): vol.Any(None, str),
        vol.Optional(SETTING_FALLBACK_NOTIFY): vol.Any(None, str),
        vol.Optional(SETTING_ALL_TAG_IDS): [str],
        vol.Optional(SETTING_PROFILE_TAGS): {str: str},
        vol.Optional(SETTING_ESCALATION_NOTIFY): vol.Any(None, str),
        vol.Optional(SETTING_CRITICAL): bool,
        vol.Optional(SETTING_ANNOUNCE_SERVICE): vol.Any(None, str),
        vol.Optional(SETTING_ANNOUNCE_HOME_ENTITY): vol.Any(None, str),
        vol.Optional(SETTING_QUIET_START): vol.Any(None, str),
        vol.Optional(SETTING_QUIET_END): vol.Any(None, str),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_save_settings(hass, connection, msg):
    """Save integration settings."""
    updates = {key: value for key, value in msg.items() if key not in ("id", "type")}
    settings = await get_runtime(hass)["manager"].async_update_settings(updates)
    await async_refresh(hass)
    return settings


@websocket_api.websocket_command(
    {
        vol.Required("type"): PREFIX + "test_notification",
        vol.Required("medication_id"): str,
        vol.Optional("alert_type", default="due"): vol.In(["due", "missed", "refill", "caregiver_confirmation", "escalation"]),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_handler
async def ws_test_notification(hass, connection, msg):
    """Send a test notification to the phone."""
    delivered = await get_runtime(hass)["alert_engine"].async_send_test_alert(
        msg["medication_id"], msg["alert_type"]
    )
    return {"delivered": delivered}


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register all websocket commands."""
    for command in (
        ws_get_state,
        ws_take,
        ws_take_all,
        ws_undo_last,
        ws_get_history,
        ws_skip,
        ws_snooze,
        ws_refill,
        ws_save_medication,
        ws_delete_medication,
        ws_delete_dose,
        ws_reset_history,
        ws_save_settings,
        ws_test_notification,
    ):
        websocket_api.async_register_command(hass, command)
