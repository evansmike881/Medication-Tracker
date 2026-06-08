"""Binary sensors for Medication Tracker."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_MEDICATION_ID, ATTR_MEDICATION_NAME, DOMAIN, SIGNAL_MEDICATIONS_UPDATED


@dataclass(frozen=True, slots=True)
class MedicationBinarySensorDescription:
    """Describe a medication binary sensor."""

    key: str
    name_suffix: str


BINARY_SENSOR_TYPES: tuple[MedicationBinarySensorDescription, ...] = (
    MedicationBinarySensorDescription(key="due_now", name_suffix="Due Now"),
    MedicationBinarySensorDescription(key="needs_refill", name_suffix="Needs Refill"),
    MedicationBinarySensorDescription(key="has_missed_dose", name_suffix="Has Missed Dose"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    manager = runtime_data["manager"]
    coordinator = runtime_data["coordinator"]
    known_entities: set[tuple[str, str]] = set()

    def build_entities() -> list[MedicationBinarySensor]:
        entities: list[MedicationBinarySensor] = []
        for medication in manager.list_medications():
            for description in BINARY_SENSOR_TYPES:
                entity_key = (medication.medication_id, description.key)
                if entity_key in known_entities:
                    continue
                known_entities.add(entity_key)
                entities.append(
                    MedicationBinarySensor(
                        coordinator=coordinator,
                        manager=manager,
                        medication_id=medication.medication_id,
                        medication_name=medication.name,
                        description=description,
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


class MedicationBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for medication state."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, manager, medication_id: str, medication_name: str, description) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._manager = manager
        self._medication_id = medication_id
        self._medication_name = medication_name
        self.entity_description = description
        self._attr_unique_id = f"{self._medication_id}_{description.key}"

    @property
    def name(self) -> str:
        """Return the entity name."""
        return f"{self._medication_name} {self.entity_description.name_suffix}"

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

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        snapshot = self._safe_snapshot
        if not snapshot:
            return None
        if self.entity_description.key == "has_missed_dose":
            return snapshot["missed_doses"] > 0
        return bool(snapshot.get(self.entity_description.key))

    @property
    def available(self) -> bool:
        """Return whether the backing medication exists."""
        return self._safe_snapshot is not None

    @property
    def _safe_snapshot(self) -> dict | None:
        """Return a snapshot when the medication still exists."""
        try:
            return self._manager.get_snapshot(self._medication_id)
        except HomeAssistantError:
            return None
