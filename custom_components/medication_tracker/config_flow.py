"""Config flow for Medication Tracker."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_TITLE
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import slugify

from .const import (
    ATTR_DATABASE_ENTRY_ID,
    ATTR_DOSAGE,
    ATTR_MEDICATION_ID,
    ATTR_MEDICATION_NAME,
    ATTR_MISSED_AFTER_MINUTES,
    ATTR_NFC_TAG_ID,
    ATTR_NOTES,
    ATTR_NOTIFICATION_ENABLED,
    ATTR_NOTIFY_SERVICE,
    ATTR_PROFILE_ID,
    ATTR_PROFILE_NAME,
    ATTR_QUANTITY,
    ATTR_REFILL_AT,
    ATTR_REMINDER_MINUTES,
    ATTR_SCHEDULES,
    DEFAULT_MISSED_AFTER_MINUTES,
    DEFAULT_REMINDER_MINUTES,
    DOMAIN,
    SIGNAL_MEDICATIONS_UPDATED,
)

CUSTOM_DATABASE_OPTION = "__custom__"


class MedicationTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Medication Tracker."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_TITLE],
                data={},
            )

        schema = vol.Schema({vol.Required(CONF_TITLE, default="Medication Tracker"): str})
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Create the options flow."""
        return MedicationTrackerOptionsFlow(config_entry)


class MedicationTrackerOptionsFlow(config_entries.OptionsFlow):
    """Manage medications from the Home Assistant backend."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow state."""
        self.config_entry = config_entry
        self._selected_database_entry_id = CUSTOM_DATABASE_OPTION
        self._selected_medication_id: str | None = None

    @property
    def _manager(self):
        """Return the live manager for this config entry."""
        return self.hass.data[DOMAIN][self.config_entry.entry_id]["manager"]

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the management menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_medication_pick_database",
                "edit_medication_select",
                "remove_medication_select",
            ],
        )

    async def async_step_add_medication_pick_database(self, user_input: dict[str, Any] | None = None):
        """Pick a bundled medication or continue with a custom entry."""
        if user_input is not None:
            self._selected_database_entry_id = user_input[ATTR_DATABASE_ENTRY_ID]
            return await self.async_step_add_medication()

        options = {
            CUSTOM_DATABASE_OPTION: "Custom medication",
            **{
                entry["id"]: f"{entry['name']} ({entry['category']})"
                for entry in self._manager.list_database_entries()
            },
        }
        return self.async_show_form(
            step_id="add_medication_pick_database",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        ATTR_DATABASE_ENTRY_ID,
                        default=CUSTOM_DATABASE_OPTION,
                    ): vol.In(options),
                }
            ),
        )

    async def async_step_add_medication(self, user_input: dict[str, Any] | None = None):
        """Add a medication from the backend UI."""
        database_entry = None
        if self._selected_database_entry_id != CUSTOM_DATABASE_OPTION:
            database_entry = self._manager.get_database_entry(self._selected_database_entry_id)

        if user_input is not None:
            await self._manager.async_add_medication(
                profile_id=user_input[ATTR_PROFILE_ID],
                profile_name=user_input[ATTR_PROFILE_NAME],
                medication_id=user_input[ATTR_MEDICATION_ID],
                medication_name=user_input[ATTR_MEDICATION_NAME],
                dosage=user_input[ATTR_DOSAGE],
                schedules=self._parse_schedules(user_input[ATTR_SCHEDULES]),
                quantity=self._coerce_optional_float(user_input[ATTR_QUANTITY]),
                refill_at=self._coerce_optional_float(user_input[ATTR_REFILL_AT]),
                notes=user_input[ATTR_NOTES],
                database_entry_id=None if self._selected_database_entry_id == CUSTOM_DATABASE_OPTION else self._selected_database_entry_id,
                nfc_tag_id=user_input[ATTR_NFC_TAG_ID],
                notification_enabled=user_input[ATTR_NOTIFICATION_ENABLED],
                notify_service=user_input[ATTR_NOTIFY_SERVICE],
                reminder_minutes=user_input[ATTR_REMINDER_MINUTES],
                missed_after_minutes=user_input[ATTR_MISSED_AFTER_MINUTES],
            )
            await self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            return self.async_create_entry(title="Medication added", data={})

        default_name = database_entry["name"] if database_entry else ""
        default_dosage = database_entry["default_dosage"] if database_entry else ""
        default_notes = database_entry["notes"] if database_entry else ""
        default_id = slugify(default_name) if default_name else ""
        return self.async_show_form(
            step_id="add_medication",
            data_schema=vol.Schema(
                {
                    vol.Required(ATTR_PROFILE_ID): str,
                    vol.Required(ATTR_PROFILE_NAME): str,
                    vol.Required(ATTR_MEDICATION_ID, default=default_id): str,
                    vol.Required(ATTR_MEDICATION_NAME, default=default_name): str,
                    vol.Required(ATTR_DOSAGE, default=default_dosage): str,
                    vol.Required(ATTR_SCHEDULES, default="08:00"): str,
                    vol.Optional(ATTR_QUANTITY, default=""): str,
                    vol.Optional(ATTR_REFILL_AT, default=""): str,
                    vol.Optional(ATTR_NOTES, default=default_notes): str,
                    vol.Optional(ATTR_NFC_TAG_ID, default=""): str,
                    vol.Optional(ATTR_NOTIFY_SERVICE, default=""): str,
                    vol.Required(ATTR_NOTIFICATION_ENABLED, default=True): bool,
                    vol.Required(ATTR_REMINDER_MINUTES, default=DEFAULT_REMINDER_MINUTES): int,
                    vol.Required(ATTR_MISSED_AFTER_MINUTES, default=DEFAULT_MISSED_AFTER_MINUTES): int,
                }
            ),
        )

    async def async_step_edit_medication_select(self, user_input: dict[str, Any] | None = None):
        """Choose a medication to edit."""
        medications = list(self._manager.list_medications())
        if not medications:
            return self.async_abort(reason="no_medications")

        if user_input is not None:
            self._selected_medication_id = user_input[ATTR_MEDICATION_ID]
            return await self.async_step_edit_medication()

        options = {item.medication_id: f"{item.profile_name}: {item.name}" for item in medications}
        return self.async_show_form(
            step_id="edit_medication_select",
            data_schema=vol.Schema({vol.Required(ATTR_MEDICATION_ID): vol.In(options)}),
        )

    async def async_step_edit_medication(self, user_input: dict[str, Any] | None = None):
        """Edit an existing medication."""
        medication = self._manager.medications[self._selected_medication_id]
        if user_input is not None:
            await self._manager.async_add_medication(
                profile_id=user_input[ATTR_PROFILE_ID],
                profile_name=user_input[ATTR_PROFILE_NAME],
                medication_id=medication.medication_id,
                medication_name=user_input[ATTR_MEDICATION_NAME],
                dosage=user_input[ATTR_DOSAGE],
                schedules=self._parse_schedules(user_input[ATTR_SCHEDULES]),
                quantity=self._coerce_optional_float(user_input[ATTR_QUANTITY]),
                refill_at=self._coerce_optional_float(user_input[ATTR_REFILL_AT]),
                notes=user_input[ATTR_NOTES],
                database_entry_id=medication.database_entry_id,
                nfc_tag_id=user_input[ATTR_NFC_TAG_ID],
                notification_enabled=user_input[ATTR_NOTIFICATION_ENABLED],
                notify_service=user_input[ATTR_NOTIFY_SERVICE],
                reminder_minutes=user_input[ATTR_REMINDER_MINUTES],
                missed_after_minutes=user_input[ATTR_MISSED_AFTER_MINUTES],
            )
            await self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            return self.async_create_entry(title="Medication updated", data={})

        return self.async_show_form(
            step_id="edit_medication",
            data_schema=vol.Schema(
                {
                    vol.Required(ATTR_PROFILE_ID, default=medication.profile_id): str,
                    vol.Required(ATTR_PROFILE_NAME, default=medication.profile_name): str,
                    vol.Required(ATTR_MEDICATION_NAME, default=medication.name): str,
                    vol.Required(ATTR_DOSAGE, default=medication.dosage): str,
                    vol.Required(ATTR_SCHEDULES, default=", ".join(medication.schedules)): str,
                    vol.Optional(ATTR_QUANTITY, default="" if medication.quantity is None else str(medication.quantity)): str,
                    vol.Optional(ATTR_REFILL_AT, default="" if medication.refill_at is None else str(medication.refill_at)): str,
                    vol.Optional(ATTR_NOTES, default=medication.notes): str,
                    vol.Optional(ATTR_NFC_TAG_ID, default=medication.nfc_tag_id or ""): str,
                    vol.Optional(ATTR_NOTIFY_SERVICE, default=medication.notify_service or ""): str,
                    vol.Required(ATTR_NOTIFICATION_ENABLED, default=medication.notification_enabled): bool,
                    vol.Required(ATTR_REMINDER_MINUTES, default=medication.reminder_minutes): int,
                    vol.Required(ATTR_MISSED_AFTER_MINUTES, default=medication.missed_after_minutes): int,
                }
            ),
        )

    async def async_step_remove_medication_select(self, user_input: dict[str, Any] | None = None):
        """Choose a medication to remove."""
        medications = list(self._manager.list_medications())
        if not medications:
            return self.async_abort(reason="no_medications")

        if user_input is not None:
            await self._manager.async_remove_medication(user_input[ATTR_MEDICATION_ID])
            await self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            return self.async_create_entry(title="Medication removed", data={})

        options = {item.medication_id: f"{item.profile_name}: {item.name}" for item in medications}
        return self.async_show_form(
            step_id="remove_medication_select",
            data_schema=vol.Schema({vol.Required(ATTR_MEDICATION_ID): vol.In(options)}),
        )

    def _parse_schedules(self, raw_value: str) -> list[str]:
        """Split a comma-separated schedule string."""
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    def _coerce_optional_float(self, raw_value: str) -> float | None:
        """Convert an optional text field to float."""
        if raw_value in {"", None}:
            return None
        return float(raw_value)
