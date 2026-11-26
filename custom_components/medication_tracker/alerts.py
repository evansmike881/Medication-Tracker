"""Alert processing for Medication Tracker."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    ACTION_CONFIRMED_PREFIX,
    ATTR_MEDICATION_ID,
    ATTR_MEDICATION_IDS,
    ATTR_NOTIFICATION_MESSAGE,
    ATTR_SCHEDULED_TIME,
    DOMAIN,
    EVENT_CAREGIVER_CONFIRMATION,
    EVENT_DOSE_DUE,
    EVENT_DOSE_ESCALATED,
    EVENT_DOSE_MISSED,
    EVENT_REFILL_NEEDED,
    SETTING_ANNOUNCE_HOME_ENTITY,
    SETTING_ANNOUNCE_SERVICE,
    SETTING_CRITICAL,
    SETTING_FALLBACK_NOTIFY,
    SIGNAL_ALERTS_UPDATED,
)
from .manager import MedicationTrackerManager

_LOGGER = logging.getLogger(__name__)

# Alert types that are time-sensitive enough to use the loud, alarm-style notification.
CRITICAL_TYPES = {"due", "missed", "escalation"}
ALARM_CHANNEL = "alarm_stream"


class MedicationAlertEngine:
    """Send notifications and emit events for due medication states."""

    def __init__(self, hass: HomeAssistant, manager: MedicationTrackerManager) -> None:
        """Initialize the alert engine."""
        self.hass = hass
        self.manager = manager
        self._active_notifications: dict[str, dict[str, Any]] = {}
        self._failed_services: set[str] = set()

    async def async_process(self) -> None:
        """Process any pending alerts. One failing alert never blocks the others."""
        # Clear notifications whose condition no longer applies (dose taken, window over).
        for notification_id, info in list(self._active_notifications.items()):
            if self.manager.alert_still_active(info["type"], info["medication_ids"]):
                continue
            await self._async_clear(notification_id)

        for alert in self.manager.get_pending_alerts():
            try:
                await self._async_emit_alert(alert)
            except Exception:  # noqa: BLE001 - never let one alert break the loop
                _LOGGER.exception("Failed to process %s alert for %s", alert.get("type"), alert.get("medication_id"))
            finally:
                # Always mark as sent, otherwise a broken target would retry every minute.
                for medication_id in alert.get("medication_ids", [alert["medication_id"]]):
                    await self.manager.async_mark_alert_sent(
                        medication_id,
                        alert["type"],
                        alert["scheduled_time"],
                    )
        async_dispatcher_send(self.hass, SIGNAL_ALERTS_UPDATED)

    async def async_send_test_alert(self, medication_id: str, alert_type: str) -> bool:
        """Send a test alert for a medication without mutating alert markers."""
        medication = self.manager.medications.get(medication_id)
        if medication is None:
            return False

        notify_service = self.manager.resolve_notify_service(medication)
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
            notify_service = self.manager.resolve_notify_service(medication, caregiver=True)
            caregiver_name = medication.caregiver_name or "The caregiver"
            message = (
                f"Test notification: {caregiver_name} should confirm the latest "
                f"{medication.name} dose for {medication.profile_name}."
            )
        elif alert_type == "escalation":
            scheduled_time = datetime.now().astimezone()
            notify_service = medication.caregiver_notify_service or self.manager.settings.get("escalation_notify_service")
            message = (
                f"Test notification: {medication.profile_name} has not taken "
                f"{medication.name} ({medication.dosage}). Please check on them."
            )
        else:
            return False

        delivered = await self._async_emit_alert(
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
        return delivered

    async def _async_emit_alert(self, alert: dict) -> bool:
        """Create a persistent notification, push to the phone and fire an event.

        Returns whether a phone notification was delivered (True when none was wanted).
        """
        message = alert["message"]
        medication_id = alert["medication_id"]
        scheduled_time = alert["scheduled_time"]
        notification_id = self._alert_notification_id(alert)

        persistent_notification.async_create(
            self.hass,
            message=message,
            title="Medication Tracker",
            notification_id=notification_id,
        )

        critical = alert["type"] in CRITICAL_TYPES and bool(self.manager.settings.get(SETTING_CRITICAL, True))
        delivered = True
        notify_service = alert.get("notify_service")
        used_service = None
        if notify_service:
            delivered = await self._async_send_mobile_notification(
                notify_service=notify_service,
                medication_id=medication_id,
                message=message,
                notification_tag=notification_id,
                actions=alert.get("actions"),
                critical=critical,
            )
            used_service = notify_service if delivered else None
            if not delivered:
                fallback = self.manager.settings.get(SETTING_FALLBACK_NOTIFY)
                if fallback and fallback != notify_service:
                    delivered = await self._async_send_mobile_notification(
                        notify_service=fallback,
                        medication_id=medication_id,
                        message=message,
                        notification_tag=notification_id,
                        actions=alert.get("actions"),
                        critical=critical,
                    )
                    used_service = fallback if delivered else None

        if alert.get("notification_suffix") != "test":
            self._active_notifications[notification_id] = {
                "medication_ids": list(alert.get("medication_ids", [medication_id])),
                "type": alert["type"],
                "notify_service": used_service,
            }

        event_payload = {
            ATTR_MEDICATION_ID: medication_id,
            ATTR_MEDICATION_IDS: alert.get("medication_ids", [medication_id]),
            ATTR_NOTIFICATION_MESSAGE: message,
            ATTR_SCHEDULED_TIME: scheduled_time.isoformat() if isinstance(scheduled_time, datetime) else None,
        }
        if alert["type"] in ("due", "missed", "escalation"):
            await self._async_announce(alert)

        if alert["type"] == "due":
            self.hass.bus.async_fire(EVENT_DOSE_DUE, event_payload)
        elif alert["type"] == "escalation":
            self.hass.bus.async_fire(EVENT_DOSE_ESCALATED, event_payload)
        elif alert["type"] == "missed":
            self.hass.bus.async_fire(EVENT_DOSE_MISSED, event_payload)
        elif alert["type"] == "refill":
            self.hass.bus.async_fire(EVENT_REFILL_NEEDED, event_payload)
        elif alert["type"] == "caregiver_confirmation":
            self.hass.bus.async_fire(EVENT_CAREGIVER_CONFIRMATION, event_payload)
        return delivered

    async def _async_announce(self, alert: dict) -> None:
        """Speak the reminder on a smart speaker (for example an Alexa notify service)."""
        settings = self.manager.settings
        service = settings.get(SETTING_ANNOUNCE_SERVICE)
        if not service or "." not in service or alert["type"] == "escalation":
            return
        if self.manager._in_quiet_hours(dt_util.now()):
            return
        home_entity = settings.get(SETTING_ANNOUNCE_HOME_ENTITY)
        if home_entity:
            state = self.hass.states.get(home_entity)
            if state is None or state.state != "home":
                return
        ids = alert.get("medication_ids", [alert["medication_id"]])
        medications = [self.manager.medications[i] for i in ids if i in self.manager.medications]
        if not medications:
            return
        names = " and ".join(", ".join(m.name for m in medications).rsplit(", ", 1))
        who = medications[0].profile_name
        spoken = (
            f"Medication reminder. {who}, please take {names}."
            if alert["type"] == "due"
            else f"{who} has missed {names}."
        )
        domain, name = service.split(".", 1)
        try:
            await self.hass.services.async_call(
                domain, name, {"message": spoken, "data": {"type": "announce"}}, blocking=True
            )
        except Exception:  # noqa: BLE001 - announcements are best effort
            _LOGGER.debug("Announcement via %s failed", service, exc_info=True)

    async def _async_clear(self, notification_id: str) -> None:
        """Remove a persistent notification and clear it from the phone too."""
        info = self._active_notifications.pop(notification_id, None)
        persistent_notification.async_dismiss(self.hass, notification_id)
        service = info.get("notify_service") if info else None
        if service and "." in service:
            domain, name = service.split(".", 1)
            try:
                await self.hass.services.async_call(
                    domain,
                    name,
                    {"message": "clear_notification", "data": {"tag": notification_id}},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001 - clearing is best effort
                _LOGGER.debug("Could not clear phone notification via %s", service, exc_info=True)

    async def async_dismiss_for_medications(self, medication_ids: list[str]) -> None:
        """Dismiss notifications (including on the phone) when doses are logged."""
        wanted = set(medication_ids)
        for notification_id, info in list(self._active_notifications.items()):
            if wanted.isdisjoint(info.get("medication_ids", [])):
                continue
            # A grouped notification stays if some of its medications are still outstanding.
            remaining = [m for m in info["medication_ids"] if m not in wanted]
            if remaining and self.manager.alert_still_active(info["type"], remaining):
                continue
            await self._async_clear(notification_id)

        for medication_id in wanted:
            for prefix in ("due", "missed", "caregiver_confirmation"):
                persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{prefix}_{medication_id}")

    def _alert_notification_id(self, alert: dict) -> str:
        """Return the notification ID for an alert payload."""
        notification_id = f"{DOMAIN}_{alert['type']}_{alert['medication_id']}"
        suffix = alert.get("notification_suffix")
        if suffix:
            notification_id = f"{notification_id}_{suffix}"
        return notification_id

    def _issue_id(self, notify_service: str) -> str:
        return f"notify_target_missing_{slugify(notify_service)}"

    async def _async_send_mobile_notification(
        self,
        *,
        notify_service: str,
        medication_id: str,
        message: str,
        notification_tag: str | None = None,
        actions: list[dict[str, str]] | None = None,
        critical: bool = False,
    ) -> bool:
        """Send a mobile app notification with action buttons. Never raises."""
        if "." not in notify_service:
            self._report_failure(notify_service, "is not a valid service name (use e.g. notify.mobile_app_phone)")
            return False
        domain, service = notify_service.split(".", 1)
        payload = {
            "message": message,
            "title": "Medication Tracker",
            "data": {
                "tag": notification_tag or f"{DOMAIN}_{medication_id}",
                "actions": actions
                or [{"action": f"{ACTION_CONFIRMED_PREFIX}{medication_id}", "title": "Taken"}],
            },
        }
        if critical:
            # Android: use the alarm volume, deliver immediately, and stay on screen until acted on.
            payload["data"].update(
                {
                    "channel": ALARM_CHANNEL,
                    "importance": "high",
                    "priority": "high",
                    "ttl": 0,
                    "sticky": "true",
                    "visibility": "public",
                }
            )
        try:
            await self.hass.services.async_call(domain, service, payload, blocking=True)
        except (HomeAssistantError, Exception) as err:  # noqa: BLE001
            self._report_failure(notify_service, f"failed: {err}")
            return False
        if notify_service in self._failed_services:
            self._failed_services.discard(notify_service)
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(notify_service))
        return True

    def _report_failure(self, notify_service: str, reason: str) -> None:
        """Warn once per service and raise a repair issue."""
        if notify_service not in self._failed_services:
            self._failed_services.add(notify_service)
            _LOGGER.warning("Medication Tracker notify service %s %s", notify_service, reason)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id(notify_service),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="notify_target_missing",
            translation_placeholders={"service": notify_service},
        )
