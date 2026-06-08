"""Bundled medication catalog helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MedicationDatabase:
    """Load a small bundled medication catalog."""

    def __init__(self) -> None:
        """Initialize the database."""
        database_path = Path(__file__).parent / "data" / "medications.json"
        payload = json.loads(database_path.read_text(encoding="utf-8"))
        self._entries: list[dict[str, Any]] = payload["medications"]
        self._by_id = {entry["id"]: entry for entry in self._entries}

    def list_entries(self) -> list[dict[str, Any]]:
        """Return all database entries."""
        return list(self._entries)

    def get(self, entry_id: str) -> dict[str, Any] | None:
        """Return a single medication entry."""
        return self._by_id.get(entry_id)

