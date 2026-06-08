"""Sensors for Medication Tracker."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import (
    ATTR_DAYS_REMAINING,
    ATTR_CAREGIVER_NAME,
    ATTR_CAREGIVER_CONFIRMATION_NEEDED,
    ATTR_CONFIRMATION_REQUIRED,
    ATTR_DOSE_COUNT,
    ATTR_DOSAGE,
    ATTR_ENTITY_BASE,
    ATTR_FORM,
    ATTR_INSTRUCTIONS,
    ATTR_LAST_TAKEN,
    ATTR_LAST_CONFIRMED_BY,
    ATTR_MEDICATION_ID,
    ATTR_MEDICATION_NAME,
    ATTR_MISSED_DOSES,
    ATTR_NEXT_DOSE,
    ATTR_NOTES,
    ATTR_PROFILE_ID,
    ATTR_PROFILE_NAME,
    ATTR_PURPOSE,
    ATTR_REFILL_AT,
    ATTR_REMAINING_QUANTITY,
    ATTR_SCHEDULES,
    ATTR_STRENGTH_OPTIONS,
    DOMAIN,
    SIGNAL_MEDICATIONS_UPDATED,
)

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_NEXT_DOSE,
        name="Next Dose",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ATTR_LAST_TAKEN,
        name="Last Dose",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key=ATTR_MISSED_DOSES,
        name="Missed Doses",
    ),
    SensorEntityDescription(
        key=ATTR_DAYS_REMAINING,
        name="Days Remaining",
        native_unit_of_measurement="d",
    ),
    SensorEntityDescription(
        key="compliance_percentage",
        name="Compliance",
        native_unit_of_measurement=PERCENTAGE,
    ),
)


SUMMARY_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="medication_count",
        name="Medication Count",
    ),
    SensorEntityDescription(
        key="tracked_medications",
        name="Tracked Medications",
    ),
    SensorEntityDescription(
        key="tracked_profiles",
        name="Tracked Profiles",
    ),
    SensorEntityDescription(
        key="tracked_caregivers",
        name="Tracked Caregivers",
    ),
    SensorEntityDescription(
        key="medication_registry",
        name="Medication Registry",
    ),
    SensorEntityDescription(
        key="due_now_count",
        name="Due Now Count",
    ),
    SensorEntityDescription(
        key="missed_dose_count",
        name="Missed Dose Count",
    ),
    SensorEntityDescription(
        key="refill_needed_count",
        name="Refill Needed Count",
    ),
    SensorEntityDescription(
        key="caregiver_confirmation_count",
        name="Caregiver Confirmations",
    ),
    SensorEntityDescription(
        key="next_due",
        name="Next Due",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Medication Tracker sensors."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    manager = runtime_data["manager"]
    coordinator = runtime_data["coordinator"]
    known_entities: set[tuple[str, str]] = set()

    def build_entities() -> list[MedicationSensor]:
        entities: list[MedicationSensor] = []
        for medication in manager.list_medications():
            for description in SENSOR_TYPES:
                entity_key = (medication.medication_id, description.key)
                if entity_key in known_entities:
                    continue
                known_entities.add(entity_key)
                entities.append(
                    MedicationSensor(
                        coordinator=coordinator,
                        manager=manager,
                        medication_id=medication.medication_id,
                        medication_name=medication.name,
                        description=description,
                    )
                )
        return entities

    async_add_entities(
        build_entities()
        + [MedicationSummarySensor(coordinator, manager, description) for description in SUMMARY_SENSOR_TYPES]
    )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_MEDICATIONS_UPDATED,
            lambda: async_add_entities(build_entities()),
        )
    )


class MedicationSensor(CoordinatorEntity, SensorEntity):
    """Represent a medication sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        manager,
        medication_id: str,
        medication_name: str,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._manager = manager
        self._medication_id = medication_id
        self._medication_name = medication_name
        self.entity_description = description
        self._attr_unique_id = f"{self._medication_id}_{self.entity_description.key}"

    @property
    def name(self) -> str:
        """Return the entity name."""
        return f"{self._medication_name} {self.entity_description.name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata."""
        snapshot = self._safe_snapshot
        return DeviceInfo(
            identifiers={(DOMAIN, self._medication_id)},
            name=snapshot[ATTR_MEDICATION_NAME] if snapshot else self._medication_name,
            manufacturer="Medication Tracker",
            model="Medication Schedule",
        )

    @property
    def native_value(self):
        """Return the current sensor value."""
        snapshot = self._safe_snapshot
        if not snapshot:
            return None
        value = snapshot.get(self.entity_description.key)
        if self.entity_description.device_class is SensorDeviceClass.TIMESTAMP and value:
            return datetime.fromisoformat(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, str | float | int | list[str] | None]:
        """Return additional sensor state attributes."""
        snapshot = self._safe_snapshot
        if not snapshot:
            return {ATTR_MEDICATION_ID: self._medication_id}
        return {
            ATTR_ENTITY_BASE: slugify(snapshot[ATTR_MEDICATION_NAME]),
            ATTR_MEDICATION_ID: snapshot[ATTR_MEDICATION_ID],
            ATTR_MEDICATION_NAME: snapshot[ATTR_MEDICATION_NAME],
            ATTR_PROFILE_ID: snapshot[ATTR_PROFILE_ID],
            ATTR_PROFILE_NAME: snapshot[ATTR_PROFILE_NAME],
            ATTR_DOSAGE: snapshot[ATTR_DOSAGE],
            ATTR_PURPOSE: snapshot[ATTR_PURPOSE],
            ATTR_FORM: snapshot[ATTR_FORM],
            ATTR_STRENGTH_OPTIONS: snapshot[ATTR_STRENGTH_OPTIONS],
            ATTR_INSTRUCTIONS: snapshot[ATTR_INSTRUCTIONS],
            ATTR_SCHEDULES: snapshot[ATTR_SCHEDULES],
            ATTR_DOSE_COUNT: snapshot[ATTR_DOSE_COUNT],
            ATTR_REMAINING_QUANTITY: snapshot[ATTR_REMAINING_QUANTITY],
            ATTR_REFILL_AT: snapshot[ATTR_REFILL_AT],
            ATTR_CAREGIVER_NAME: snapshot[ATTR_CAREGIVER_NAME],
            ATTR_CONFIRMATION_REQUIRED: snapshot[ATTR_CONFIRMATION_REQUIRED],
            ATTR_CAREGIVER_CONFIRMATION_NEEDED: snapshot[ATTR_CAREGIVER_CONFIRMATION_NEEDED],
            ATTR_LAST_CONFIRMED_BY: snapshot[ATTR_LAST_CONFIRMED_BY],
            ATTR_NOTES: snapshot[ATTR_NOTES],
        }

    @property
    def available(self) -> bool:
        """Return whether the medication still exists."""
        return self._safe_snapshot is not None

    @property
    def _safe_snapshot(self) -> dict | None:
        """Return a snapshot when the backing medication still exists."""
        try:
            return self._manager.get_snapshot(self._medication_id)
        except HomeAssistantError:
            return None


class MedicationSummarySensor(CoordinatorEntity, SensorEntity):
    """Aggregate summary sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, manager, description: SensorEntityDescription) -> None:
        """Initialize a summary sensor."""
        super().__init__(coordinator)
        self._manager = manager
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_summary_{description.key}"

    @property
    def name(self) -> str:
        """Return the entity name."""
        return f"Medication Tracker {self.entity_description.name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return integration device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, "summary")},
            name="Medication Tracker",
            manufacturer="Medication Tracker",
            model="Dashboard Summary",
        )

    @property
    def native_value(self):
        """Return the sensor value."""
        summary = self._manager.get_summary()
        value = summary.get(self.entity_description.key)
        if self.entity_description.device_class is SensorDeviceClass.TIMESTAMP and value:
            return datetime.fromisoformat(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Return overview attributes for the summary device."""
        if self.entity_description.key not in {
            "tracked_medications",
            "tracked_profiles",
            "tracked_caregivers",
            "medication_registry",
        }:
            return None

        medications = list(self._manager.list_medications())
        medication_rows = [
            {
                "profile": medication.profile_name,
                "medication": medication.name,
                "medication_id": medication.medication_id,
                "schedules": medication.schedules,
            }
            for medication in medications
        ]
        profiles = sorted({medication.profile_name for medication in medications})

        if self.entity_description.key == "tracked_medications":
            return {
                "medications": medication_rows,
                "medication_names": [row["medication"] for row in medication_rows],
            }

        if self.entity_description.key == "medication_registry":
            return {
                "rows": self._manager.get_registry_rows(),
                "registry_count": len(medications),
            }

        if self.entity_description.key == "tracked_caregivers":
            caregivers = sorted({medication.caregiver_name for medication in medications if medication.caregiver_name})
            return {
                "caregivers": caregivers,
                "medication_count_by_caregiver": {
                    caregiver: sum(1 for medication in medications if medication.caregiver_name == caregiver)
                    for caregiver in caregivers
                },
            }

        return {
            "profiles": profiles,
            "medication_count_by_profile": {
                profile: sum(1 for medication in medications if medication.profile_name == profile)
                for profile in profiles
            },
        }
