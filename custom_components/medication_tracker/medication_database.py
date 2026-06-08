"""Bundled medication catalog helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant


class MedicationDatabase:
    """Load a small bundled medication catalog."""

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        """Initialize the database."""
        self._entries: list[dict[str, Any]] = entries or []
        self._by_id = {entry["id"]: entry for entry in self._entries}

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "MedicationDatabase":
        """Load the bundled database without blocking the event loop."""
        database_path = Path(__file__).parent / "data" / "medications.json"
        payload = await hass.async_add_executor_job(_read_database_payload, database_path)
        return cls(payload["medications"])

    def list_entries(self) -> list[dict[str, Any]]:
        """Return all database entries."""
        return list(self._entries)

    def get(self, entry_id: str) -> dict[str, Any] | None:
        """Return a single medication entry."""
        return self._by_id.get(entry_id)


def _read_database_payload(database_path: Path) -> dict[str, Any]:
    """Read the bundled JSON database from disk."""
    return json.loads(database_path.read_text(encoding="utf-8"))
