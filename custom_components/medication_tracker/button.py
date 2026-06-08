"""Button entities for Medication Tracker."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_MEDICATION_NAME, DOMAIN, SIGNAL_MEDICATIONS_UPDATED


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up medication buttons."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    manager = runtime_data["manager"]
    coordinator = runtime_data["coordinator"]
    alert_engine = runtime_data["alert_engine"]
    known_entities: set[str] = set()

    def build_entities() -> list[MedicationLogDoseButton]:
        entities: list[MedicationLogDoseButton] = []
        for medication in manager.list_medications():
            if medication.medication_id in known_entities:
                continue
            known_entities.add(medication.medication_id)
            entities.append(
                MedicationLogDoseButton(
                    coordinator=coordinator,
                    manager=manager,
                    alert_engine=alert_engine,
                    medication_id=medication.medication_id,
                    medication_name=medication.name,
                )
            )
        return entities

    async_add_entities(build_entities())
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_MEDICATIONS_UPDATED,
            lambda: async_add_entities(build_entities()),
        )
    )


class MedicationLogDoseButton(CoordinatorEntity, ButtonEntity):
    """Log a medication dose from the UI."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, manager, alert_engine, medication_id: str, medication_name: str) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._manager = manager
        self._alert_engine = alert_engine
        self._medication_id = medication_id
        self._medication_name = medication_name
        self._attr_unique_id = f"{medication_id}_log_dose"
        self._attr_name = f"{medication_name} Log Dose"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        snapshot = self._safe_snapshot
        return DeviceInfo(
            identifiers={(DOMAIN, self._medication_id)},
            name=snapshot[ATTR_MEDICATION_NAME] if snapshot else self._medication_name,
            manufacturer="Medication Tracker",
            model="Medication Schedule",
        )

    async def async_press(self) -> None:
        """Log a dose immediately."""
        await self._manager.async_log_dose(self._medication_id)
        self._alert_engine.dismiss_for_medication(self._medication_id)
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        """Return whether the medication still exists."""
        return self._safe_snapshot is not None

    @property
    def _safe_snapshot(self) -> dict | None:
        """Return a snapshot when the medication still exists."""
        try:
            return self._manager.get_snapshot(self._medication_id)
        except HomeAssistantError:
            return None
