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
from .runtime import async_skip, async_snooze, async_take, async_take_all

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
        entity_registry_enabled_default=False,
        name="Test Due Notification",
        icon="mdi:bell-ring-outline",
    ),
    ButtonEntityDescription(
        key="test_missed_notification",
        entity_registry_enabled_default=False,
        name="Test Missed Notification",
        icon="mdi:bell-alert-outline",
    ),
    ButtonEntityDescription(
        key="test_refill_notification",
        entity_registry_enabled_default=False,
        name="Test Refill Notification",
        icon="mdi:bottle-tonic-plus-outline",
    ),
    ButtonEntityDescription(
        key="test_caregiver_notification",
        entity_registry_enabled_default=False,
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

    async_add_entities([TakeAllDueButton(coordinator, manager)])
    async_add_entities(build_entities())
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_MEDICATIONS_UPDATED,
            # Signals can be sent from outside the event loop; entities must be added in it.
            lambda: hass.loop.call_soon_threadsafe(lambda: async_add_entities(build_entities())),
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
        key = self.entity_description.key
        if key == "log_dose":
            await async_take(self.hass, self._medication_id, source="button")
        elif key == "skip_dose":
            await async_skip(self.hass, self._medication_id)
        elif key == "snooze_10_minutes":
            await async_snooze(self.hass, self._medication_id, 10)
        elif key.startswith("test_"):
            alert_type = {
                "test_due_notification": "due",
                "test_missed_notification": "missed",
                "test_refill_notification": "refill",
                "test_caregiver_notification": "caregiver_confirmation",
            }[key]
            delivered = await self._alert_engine.async_send_test_alert(self._medication_id, alert_type)
            if not delivered:
                raise HomeAssistantError(
                    "The phone notification could not be sent. Check the notify service "
                    "name in Medication Tracker settings (see Settings > Repairs)."
                )

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


class TakeAllDueButton(CoordinatorEntity, ButtonEntity):
    """Mark everything that is currently due as taken."""

    _attr_has_entity_name = True
    _attr_name = "Take All Due"
    _attr_icon = "mdi:pill-multiple"

    def __init__(self, coordinator, manager) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._manager = manager
        self._attr_unique_id = "summary_take_all_due"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach to the summary device."""
        return DeviceInfo(
            identifiers={(DOMAIN, "summary")},
            name="Medication Tracker",
            manufacturer="Medication Tracker",
            model="Medication Summary",
        )

    async def async_press(self) -> None:
        """Log every outstanding dose."""
        await async_take_all(self.hass, source="button")
