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
    EVENT_CAREGIVER_CONFIRMATION,
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

    async def async_send_test_alert(self, medication_id: str, alert_type: str) -> None:
        """Send a test alert for a medication without mutating alert markers."""
        medication = self.manager.medications.get(medication_id)
        if medication is None:
            return

        notify_service = medication.notify_service
        scheduled_time = None

        if alert_type == "due":
            scheduled_time = datetime.now().astimezone()
            message = (
                f"Test notification: {medication.profile_name} is due to take "
                f"{medication.name} ({medication.dosage}) now."
            )
        elif alert_type == "missed":
            scheduled_time = datetime.now().astimezone()
            message = (
                f"Test notification: {medication.profile_name} missed a scheduled "
                f"dose of {medication.name} ({medication.dosage})."
            )
        elif alert_type == "refill":
            remaining = medication.quantity if medication.quantity is not None else 0
            message = (
                f"Test notification: {medication.name} refill alert for "
                f"{medication.profile_name}. Remaining doses: {remaining:g}."
            )
        elif alert_type == "caregiver_confirmation":
            scheduled_time = datetime.now().astimezone()
            notify_service = medication.caregiver_notify_service or medication.notify_service
            caregiver_name = medication.caregiver_name or "The caregiver"
            message = (
                f"Test notification: {caregiver_name} should confirm the latest "
                f"{medication.name} dose for {medication.profile_name}."
            )
        else:
            return

        await self._async_emit_alert(
            {
                "type": alert_type,
                "medication_id": medication_id,
                "notify_service": notify_service,
                "scheduled_time": scheduled_time,
                "message": message,
                "notification_suffix": "test",
            }
        )
        async_dispatcher_send(self.hass, SIGNAL_ALERTS_UPDATED)

    async def _async_emit_alert(self, alert: dict) -> None:
        """Create a persistent notification and fire an event."""
        message = alert["message"]
        medication_id = alert["medication_id"]
        scheduled_time = alert["scheduled_time"]
        notification_id = self._notification_id(
            alert["type"],
            medication_id,
            scheduled_time,
            suffix=alert.get("notification_suffix"),
        )

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
        elif alert["type"] == "caregiver_confirmation":
            self.hass.bus.async_fire(EVENT_CAREGIVER_CONFIRMATION, event_payload)

    def dismiss_for_medication(self, medication_id: str) -> None:
        """Dismiss common due and missed notifications when a dose is logged."""
        for prefix in ("due", "missed", "caregiver_confirmation"):
            persistent_notification.async_dismiss(
                self.hass,
                f"{DOMAIN}_{prefix}_{medication_id}",
            )

    def _notification_id(
        self,
        alert_type: str,
        medication_id: str,
        scheduled_time: datetime | None,
        suffix: str | None = None,
    ) -> str:
        """Return a deterministic notification ID."""
        notification_id = f"{DOMAIN}_{alert_type}_{medication_id}"
        if suffix:
            notification_id = f"{notification_id}_{suffix}"
        return notification_id

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
