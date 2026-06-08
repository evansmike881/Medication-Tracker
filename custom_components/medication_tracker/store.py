"""Persistent storage for Medication Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import Medication


class MedicationTrackerStore:
    """Wrap Home Assistant storage helpers."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._store = Store[dict[str, Any]](hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_load(self) -> dict[str, Medication]:
        """Load medications keyed by medication_id."""
        payload = await self._store.async_load() or {}
        medications = payload.get("medications", [])
        return {
            item["medication_id"]: Medication.from_dict(item)
            for item in medications
        }

    async def async_save(self, medications: dict[str, Medication]) -> None:
        """Persist medications."""
        await self._store.async_save(
            {
                "medications": [
                    medication.as_dict() for medication in medications.values()
                ]
            }
        )
