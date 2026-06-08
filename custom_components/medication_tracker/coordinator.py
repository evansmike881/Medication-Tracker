"""Coordinator for Medication Tracker."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL_MINUTES, DOMAIN
from .manager import MedicationTrackerManager
from .alerts import MedicationAlertEngine


class MedicationTrackerCoordinator(DataUpdateCoordinator[None]):
    """Coordinate sensor refreshes."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: MedicationTrackerManager,
        alert_engine: MedicationAlertEngine,
    ) -> None:
        """Initialize the coordinator."""
        self.manager = manager
        self.alert_engine = alert_engine
        super().__init__(
            hass,
            logger=hass.data[DOMAIN]["logger"],
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> None:
        """Refresh coordinator data."""
        await self.alert_engine.async_process()
        return None
