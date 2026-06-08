"""Alert processing for Medication Tracker."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ATTR_MEDICATION_ID,
    ATTR_NOTIFICATION_MESSAGE,
    ATTR_SCHEDULED_TIME,
    DOMAIN,
    EVENT_DOSE_DUE,
    EVENT_DOSE_MISSED,
    EVENT_REFILL_NEEDED,
    SIGNAL_ALERTS_UPDATED,
)
from .manager import MedicationTrackerManager


class MedicationAlertEngine:
    """Send notifications and emit events for due medication states."""

    def __init__(self, hass: HomeAssistant, manager: MedicationTrackerManager) -> None:
        """Initialize the alert engine."""
        self.hass = hass
        self.manager = manager

    async def async_process(self) -> None:
        """Process any pending alerts."""
        for alert in self.manager.get_pending_alerts():
            await self._async_emit_alert(alert)
            await self.manager.async_mark_alert_sent(
                alert["medication_id"],
                alert["type"],
                alert["scheduled_time"],
            )
        async_dispatcher_send(self.hass, SIGNAL_ALERTS_UPDATED)

    async def _async_emit_alert(self, alert: dict) -> None:
        """Create a persistent notification and fire an event."""
        message = alert["message"]
        medication_id = alert["medication_id"]
        scheduled_time = alert["scheduled_time"]
        notification_id = self._notification_id(alert["type"], medication_id, scheduled_time)

        persistent_notification.async_create(
            self.hass,
            message=message,
            title="Medication Tracker",
            notification_id=notification_id,
        )

        notify_service = alert.get("notify_service")
        if notify_service:
            await self._async_send_mobile_notification(
                notify_service=notify_service,
                medication_id=medication_id,
                message=message,
            )

        event_payload = {
            ATTR_MEDICATION_ID: medication_id,
            ATTR_NOTIFICATION_MESSAGE: message,
            ATTR_SCHEDULED_TIME: scheduled_time.isoformat() if isinstance(scheduled_time, datetime) else None,
        }
        if alert["type"] == "due":
            self.hass.bus.async_fire(EVENT_DOSE_DUE, event_payload)
        elif alert["type"] == "missed":
            self.hass.bus.async_fire(EVENT_DOSE_MISSED, event_payload)
        elif alert["type"] == "refill":
            self.hass.bus.async_fire(EVENT_REFILL_NEEDED, event_payload)

    def dismiss_for_medication(self, medication_id: str) -> None:
        """Dismiss common due and missed notifications when a dose is logged."""
        for prefix in ("due", "missed"):
            persistent_notification.async_dismiss(
                self.hass,
                f"{DOMAIN}_{prefix}_{medication_id}",
            )

    def _notification_id(
        self,
        alert_type: str,
        medication_id: str,
        scheduled_time: datetime | None,
    ) -> str:
        """Return a deterministic notification ID."""
        return f"{DOMAIN}_{alert_type}_{medication_id}"

    async def _async_send_mobile_notification(
        self,
        *,
        notify_service: str,
        medication_id: str,
        message: str,
    ) -> None:
        """Send a mobile app notification with a confirm action."""
        if "." not in notify_service:
            return
        domain, service = notify_service.split(".", 1)
        await self.hass.services.async_call(
            domain,
            service,
            {
                "message": message,
                "data": {
                    "tag": f"{DOMAIN}_{medication_id}",
                    "actions": [
                        {
                            "action": f"MEDICATION_CONFIRMED_{medication_id}",
                            "title": "Taken",
                        }
                    ],
                },
            },
            blocking=False,
        )
