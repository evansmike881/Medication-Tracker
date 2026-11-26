"""Shared runtime helpers and user actions.

Services, notification buttons, NFC tags, Assist intents and the panel all go through
these functions so every route behaves identically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ATTR_MEDICATION_ID,
    ATTR_MEDICATION_IDS,
    ATTR_SOURCE,
    ATTR_TAKEN_AT,
    DOMAIN,
    EVENT_DOSE_TAKEN,
    SIGNAL_MEDICATIONS_UPDATED,
)


async def async_context_user_name(hass: HomeAssistant, context: Any) -> str | None:
    """Return the name of the Home Assistant user behind a service call, if any."""
    user_id = getattr(context, "user_id", None)
    if not user_id:
        return None
    try:
        user = await hass.auth.async_get_user(user_id)
    except Exception:  # noqa: BLE001
        return None
    return user.name if user else None


def get_runtime(hass: HomeAssistant) -> dict[str, Any]:
    """Return the runtime payload for the loaded config entry."""
    for value in hass.data.get(DOMAIN, {}).values():
        if isinstance(value, dict) and "manager" in value:
            return value
    raise HomeAssistantError("Medication Tracker is not set up.")


async def async_refresh(hass: HomeAssistant) -> None:
    """Re-run alert processing and tell entities to update."""
    runtime = get_runtime(hass)
    await runtime["coordinator"].async_request_refresh()
    async_dispatcher_send(hass, SIGNAL_MEDICATIONS_UPDATED)


async def async_take(
    hass: HomeAssistant,
    medication_id: str,
    *,
    source: str = "manual",
    confirmed_by: str | None = None,
    taken_at: datetime | None = None,
    allow_duplicate: bool = False,
    taken_by: str | None = None,
) -> None:
    """Log one dose and clear its reminders."""
    runtime = get_runtime(hass)
    await runtime["manager"].async_log_dose(
        medication_id,
        taken_at,
        source=source,
        confirmed_by=confirmed_by,
        allow_duplicate=allow_duplicate,
        taken_by=taken_by,
    )
    await runtime["alert_engine"].async_dismiss_for_medications([medication_id])
    hass.bus.async_fire(
        EVENT_DOSE_TAKEN,
        {
            ATTR_MEDICATION_ID: medication_id,
            ATTR_MEDICATION_IDS: [medication_id],
            ATTR_SOURCE: source,
            "taken_by": taken_by,
        },
    )
    await async_refresh(hass)


async def async_take_all(
    hass: HomeAssistant,
    *,
    profile_id: str | None = None,
    medication_ids: list[str] | None = None,
    source: str = "manual",
    confirmed_by: str | None = None,
    taken_by: str | None = None,
) -> dict[str, list[str]]:
    """Log a dose for everything that is due or overdue (optionally per profile)."""
    runtime = get_runtime(hass)
    result = await runtime["manager"].async_log_outstanding(
        profile_id=profile_id,
        medication_ids=medication_ids,
        source=source,
        confirmed_by=confirmed_by,
        taken_by=taken_by,
    )
    if result["logged"]:
        await runtime["alert_engine"].async_dismiss_for_medications(result["logged"])
        hass.bus.async_fire(
            EVENT_DOSE_TAKEN,
            {
                ATTR_MEDICATION_ID: result["logged"][0],
                ATTR_MEDICATION_IDS: result["logged"],
                ATTR_SOURCE: source,
                "taken_by": taken_by,
            },
        )
    await async_refresh(hass)
    return result


async def async_skip(hass: HomeAssistant, medication_id: str, scheduled_time: datetime | None = None) -> None:
    """Skip the current occurrence."""
    runtime = get_runtime(hass)
    await runtime["manager"].async_skip_medication_occurrence(medication_id, scheduled_time)
    await runtime["alert_engine"].async_dismiss_for_medications([medication_id])
    await async_refresh(hass)


async def async_snooze(hass: HomeAssistant, medication_id: str, minutes: int) -> None:
    """Snooze reminders."""
    runtime = get_runtime(hass)
    await runtime["manager"].async_snooze_medication(medication_id, minutes)
    await runtime["alert_engine"].async_dismiss_for_medications([medication_id])
    await async_refresh(hass)


async def async_undo_last(hass: HomeAssistant, medication_id: str) -> None:
    """Remove the most recent dose and let reminders resume if it is still due."""
    runtime = get_runtime(hass)
    await runtime["manager"].async_undo_last(medication_id)
    await async_refresh(hass)


__all__ = [
    "async_context_user_name",
    "async_undo_last",
    "ATTR_TAKEN_AT",
    "async_refresh",
    "async_skip",
    "async_snooze",
    "async_take",
    "async_take_all",
    "get_runtime",
]
