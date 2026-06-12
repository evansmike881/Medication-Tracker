"""Button entities for Medication Tracker."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_MEDICATION_NAME, DOMAIN, SIGNAL_MEDICATIONS_UPDATED

BUTTON_TYPES: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="log_dose",
        name="Log Dose",
        icon="mdi:pill",
    ),
    ButtonEntityDescription(
        key="skip_dose",
        name="Skip Dose",
        icon="mdi:skip-next-circle-outline",
    ),
    ButtonEntityDescription(
        key="snooze_10_minutes",
        name="Snooze 10 Minutes",
        icon="mdi:timer-sand",
    ),
    ButtonEntityDescription(
        key="test_due_notification",
        name="Test Due Notification",
        icon="mdi:bell-ring-outline",
    ),
    ButtonEntityDescription(
        key="test_missed_notification",
        name="Test Missed Notification",
        icon="mdi:bell-alert-outline",
    ),
    ButtonEntityDescription(
        key="test_refill_notification",
        name="Test Refill Notification",
        icon="mdi:bottle-tonic-plus-outline",
    ),
    ButtonEntityDescription(
        key="test_caregiver_notification",
        name="Test Caregiver Notification",
        icon="mdi:account-alert-outline",
    ),
)


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
    known_entities: set[tuple[str, str]] = set()

    def build_entities() -> list[MedicationActionButton]:
        entities: list[MedicationActionButton] = []
        for medication in manager.list_medications():
            for description in BUTTON_TYPES:
                entity_key = (medication.medication_id, description.key)
                if entity_key in known_entities:
                    continue
                known_entities.add(entity_key)
                entities.append(
                    MedicationActionButton(
                        coordinator=coordinator,
                        manager=manager,
                        alert_engine=alert_engine,
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


class MedicationActionButton(CoordinatorEntity, ButtonEntity):
    """Run an action for a medication from the UI."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        manager,
        alert_engine,
        medication_id: str,
        medication_name: str,
        description: ButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._manager = manager
        self._alert_engine = alert_engine
        self._medication_id = medication_id
        self._medication_name = medication_name
        self.entity_description = description
        self._attr_unique_id = f"{medication_id}_{description.key}"

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
        """Run the configured medication action."""
        if self.entity_description.key == "log_dose":
            await self._manager.async_log_dose(self._medication_id)
            self._alert_engine.dismiss_for_medication(self._medication_id)
        elif self.entity_description.key == "skip_dose":
            await self._manager.async_skip_medication_occurrence(self._medication_id)
            self._alert_engine.dismiss_for_medication(self._medication_id)
        elif self.entity_description.key == "snooze_10_minutes":
            await self._manager.async_snooze_medication(self._medication_id, 10)
            self._alert_engine.dismiss_for_medication(self._medication_id)
        elif self.entity_description.key == "test_due_notification":
            await self._alert_engine.async_send_test_alert(self._medication_id, "due")
        elif self.entity_description.key == "test_missed_notification":
            await self._alert_engine.async_send_test_alert(self._medication_id, "missed")
        elif self.entity_description.key == "test_refill_notification":
            await self._alert_engine.async_send_test_alert(self._medication_id, "refill")
        elif self.entity_description.key == "test_caregiver_notification":
            await self._alert_engine.async_send_test_alert(self._medication_id, "caregiver_confirmation")
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
