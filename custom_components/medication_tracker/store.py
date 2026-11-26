"""Persistent storage for Medication Tracker."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DEFAULT_SETTINGS, STORAGE_KEY, STORAGE_VERSION
from .models import Group, Medication


class MedicationTrackerStore:
    """Wrap Home Assistant storage helpers."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_load_all(self) -> tuple[dict[str, Medication], dict[str, Any], dict[str, Group]]:
        """Load medications keyed by medication_id, integration settings and groups."""
        payload = await self._store.async_load() or {}
        medications = {
            item["medication_id"]: Medication.from_dict(item)
            for item in payload.get("medications", [])
        }
        settings = deepcopy(DEFAULT_SETTINGS)
        stored_settings = payload.get("settings")
        if isinstance(stored_settings, dict):
            for key in DEFAULT_SETTINGS:
                if key in stored_settings and stored_settings[key] is not None:
                    settings[key] = stored_settings[key]
        groups = {
            item["group_id"]: Group.from_dict(item)
            for item in payload.get("groups", [])
        }
        return medications, settings, groups

    async def async_load(self) -> dict[str, Medication]:
        """Load medications keyed by medication_id."""
        medications, _settings, _groups = await self.async_load_all()
        return medications

    async def async_save(
        self,
        medications: dict[str, Medication],
        settings: dict[str, Any] | None = None,
        groups: dict[str, Group] | None = None,
    ) -> None:
        """Persist medications, settings and groups."""
        await self._store.async_save(
            {
                "medications": [
                    medication.as_dict() for medication in medications.values()
                ],
                "settings": settings if settings is not None else deepcopy(DEFAULT_SETTINGS),
                "groups": [group.as_dict() for group in (groups or {}).values()],
            }
        )
