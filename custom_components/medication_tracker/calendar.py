"""Calendar entities for Medication Tracker."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up calendar entities."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            MedicationScheduleCalendar(
                coordinator=runtime_data["coordinator"],
                manager=runtime_data["manager"],
            )
        ]
    )


class MedicationScheduleCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar representation of upcoming medication schedules."""

    _attr_has_entity_name = True
    _attr_name = "Schedule"
    _attr_unique_id = f"{DOMAIN}_schedule_calendar"

    def __init__(self, coordinator, manager) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator)
        self._manager = manager
        self._attr_event = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, "summary")},
            name="Medication Tracker",
            manufacturer="Medication Tracker",
            model="Dashboard Summary",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = dt_util.now()
        events = self._calendar_events(now - timedelta(minutes=1), now + timedelta(days=30))
        for event in events:
            if event.end >= now:
                return event
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        return self._calendar_events(start_date, end_date)

    def _calendar_events(self, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        """Build grouped medication events for the requested range."""
        grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)

        for medication in self._manager.list_medications():
            current_date = max(medication.start_date, start_date.date())
            while current_date <= end_date.date():
                for schedule in medication.schedules:
                    occurrence = self._manager._combine(current_date, schedule)
                    if occurrence < start_date or occurrence >= end_date:
                        continue
                    if occurrence.isoformat() in medication.skipped_occurrences:
                        continue
                    grouped[(medication.profile_name, occurrence.isoformat())].append(
                        {
                            "medication_name": medication.name,
                            "dosage": medication.dosage,
                            "purpose": medication.purpose,
                            "occurrence": occurrence,
                            "reminder_minutes": medication.reminder_minutes,
                        }
                    )
                current_date += timedelta(days=1)

        calendar_events: list[CalendarEvent] = []
        for (profile_name, _occurrence_key), items in sorted(grouped.items(), key=lambda item: item[0][1]):
            sorted_items = sorted(items, key=lambda item: str(item["medication_name"]).lower())
            start = sorted_items[0]["occurrence"]
            duration_minutes = max(int(item["reminder_minutes"]) for item in sorted_items)
            end = start + timedelta(minutes=max(duration_minutes, 1))
            summary = (
                f"{profile_name}: {', '.join(str(item['medication_name']) for item in sorted_items)}"
            )
            description = "\n".join(
                f"- {item['medication_name']} ({item['dosage']})"
                + (f": {item['purpose']}" if item["purpose"] else "")
                for item in sorted_items
            )
            calendar_events.append(
                CalendarEvent(
                    summary=summary,
                    start=start,
                    end=end,
                    description=description,
                )
            )

        return calendar_events
