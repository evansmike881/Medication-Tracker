"""Config flow for Medication Tracker."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import selector

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

CONF_DISPLAY_NAME = "name"
CUSTOM_DATABASE_OPTION = "__custom__"


class MedicationTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Medication Tracker."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_DISPLAY_NAME],
                data={},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DISPLAY_NAME, default="Medication Tracker"): str,
                }
            ),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return MedicationTrackerOptionsFlow(config_entry)


class MedicationTrackerOptionsFlow(config_entries.OptionsFlow):
    """Manage medications from the backend UI."""

    def __init__(self, config_entry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry
        self._selected_database_entry_id = CUSTOM_DATABASE_OPTION
        self._selected_medication_id = None
        self._selected_profile_id = None
        self._selected_profile_name = None

    @property
    def _runtime(self):
        """Return runtime data for this config entry."""
        return self.hass.data[DOMAIN][self._config_entry.entry_id]

    @property
    def _manager(self):
        """Return the live manager."""
        return self._runtime["manager"]

    async def async_step_init(self, user_input=None):
        """Show the management menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_medication_pick_database",
                "edit_medication_select",
                "remove_medication_select",
            ],
        )

    async def async_step_add_medication_pick_database(self, user_input=None):
        """Pick a bundled medication template or a custom entry."""
        if user_input is not None:
            self._selected_database_entry_id = user_input[ATTR_DATABASE_ENTRY_ID]
            return await self.async_step_add_medication_pick_profile()

        options = {CUSTOM_DATABASE_OPTION: "Custom medication"}
        for entry in self._manager.list_database_entries():
            options[entry["id"]] = f'{entry["name"]} ({entry["category"]})'

        return self.async_show_form(
            step_id="add_medication_pick_database",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        ATTR_DATABASE_ENTRY_ID,
                        default=CUSTOM_DATABASE_OPTION,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=value, label=label)
                                for value, label in options.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_add_medication_pick_profile(self, user_input=None):
        """Choose an existing profile or create a new one."""
        profiles = self._profiles()
        if not profiles:
            return await self.async_step_add_medication_profile_new()

        if user_input is not None:
            profile_choice = user_input["profile_choice"]
            if profile_choice == "__new__":
                return await self.async_step_add_medication_profile_new()

            self._selected_profile_id, self._selected_profile_name = profile_choice.split("|", 1)
            return await self.async_step_add_medication()

        options = [
            selector.SelectOptionDict(value="__new__", label="Create a new person or pet")
        ]
        options.extend(
            selector.SelectOptionDict(
                value=f"{profile_id}|{profile_name}",
                label=f"{profile_name} ({profile_id})",
            )
            for profile_id, profile_name in profiles.items()
        )
        return self.async_show_form(
            step_id="add_medication_pick_profile",
            data_schema=vol.Schema(
                {
                    vol.Required("profile_choice", default="__new__"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_add_medication_profile_new(self, user_input=None):
        """Create a new profile before adding medication."""
        if user_input is not None:
            self._selected_profile_id = user_input[ATTR_PROFILE_ID]
            self._selected_profile_name = user_input[ATTR_PROFILE_NAME]
            return await self.async_step_add_medication()

        return self.async_show_form(
            step_id="add_medication_profile_new",
            data_schema=vol.Schema(
                {
                    vol.Required(ATTR_PROFILE_ID): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(ATTR_PROFILE_NAME): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                }
            ),
        )

    async def async_step_add_medication(self, user_input=None):
        """Add a medication."""
        database_entry = None
        if self._selected_database_entry_id != CUSTOM_DATABASE_OPTION:
            database_entry = self._manager.get_database_entry(self._selected_database_entry_id)

        if user_input is not None:
            await self._manager.async_add_medication(
                profile_id=self._selected_profile_id or user_input[ATTR_PROFILE_ID],
                profile_name=self._selected_profile_name or user_input[ATTR_PROFILE_NAME],
                medication_id=user_input[ATTR_MEDICATION_ID],
                medication_name=user_input[ATTR_MEDICATION_NAME],
                dosage=user_input[ATTR_DOSAGE],
                schedules=self._parse_schedules(user_input[ATTR_SCHEDULES]),
                quantity=self._coerce_optional_float(user_input.get(ATTR_QUANTITY)),
                refill_at=self._coerce_optional_float(user_input.get(ATTR_REFILL_AT)),
                notes=user_input.get(ATTR_NOTES, ""),
                database_entry_id=(
                    None
                    if self._selected_database_entry_id == CUSTOM_DATABASE_OPTION
                    else self._selected_database_entry_id
                ),
                nfc_tag_id=self._empty_to_none(user_input.get(ATTR_NFC_TAG_ID)),
                notification_enabled=user_input.get(ATTR_NOTIFICATION_ENABLED, True),
                notify_service=self._empty_to_none(user_input.get(ATTR_NOTIFY_SERVICE)),
                reminder_minutes=int(user_input.get(ATTR_REMINDER_MINUTES, DEFAULT_REMINDER_MINUTES)),
                missed_after_minutes=int(
                    user_input.get(ATTR_MISSED_AFTER_MINUTES, DEFAULT_MISSED_AFTER_MINUTES)
                ),
            )
            await self._runtime["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            return self.async_create_entry(title="", data={})

        default_name = database_entry["name"] if database_entry else ""
        default_dosage = database_entry["default_dosage"] if database_entry else ""
        default_notes = database_entry["notes"] if database_entry else ""
        default_id = self._slugify(default_name) if default_name else ""

        return self.async_show_form(
            step_id="add_medication",
            data_schema=self._build_medication_schema(
                profile_locked=self._selected_profile_id is not None,
                medication_id=default_id,
                medication_name=default_name,
                dosage=default_dosage,
                schedules="08:00",
                quantity="",
                refill_at="",
                notes=default_notes,
                nfc_tag_id="",
                notify_service="",
                notification_enabled=True,
                reminder_minutes=DEFAULT_REMINDER_MINUTES,
                missed_after_minutes=DEFAULT_MISSED_AFTER_MINUTES,
            ),
        )

    async def async_step_edit_medication_select(self, user_input=None):
        """Select a medication to edit."""
        medications = list(self._manager.list_medications())
        if not medications:
            return self.async_abort(reason="no_medications")

        if user_input is not None:
            self._selected_medication_id = user_input[ATTR_MEDICATION_ID]
            return await self.async_step_edit_medication()

        options = {
            item.medication_id: f"{item.profile_name}: {item.name}"
            for item in medications
        }
        return self.async_show_form(
            step_id="edit_medication_select",
            data_schema=vol.Schema({vol.Required(ATTR_MEDICATION_ID): vol.In(options)}),
        )

    async def async_step_edit_medication(self, user_input=None):
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
                quantity=self._coerce_optional_float(user_input.get(ATTR_QUANTITY)),
                refill_at=self._coerce_optional_float(user_input.get(ATTR_REFILL_AT)),
                notes=user_input.get(ATTR_NOTES, ""),
                database_entry_id=medication.database_entry_id,
                nfc_tag_id=self._empty_to_none(user_input.get(ATTR_NFC_TAG_ID)),
                notification_enabled=user_input.get(ATTR_NOTIFICATION_ENABLED, True),
                notify_service=self._empty_to_none(user_input.get(ATTR_NOTIFY_SERVICE)),
                reminder_minutes=int(user_input.get(ATTR_REMINDER_MINUTES, medication.reminder_minutes)),
                missed_after_minutes=int(
                    user_input.get(ATTR_MISSED_AFTER_MINUTES, medication.missed_after_minutes)
                ),
            )
            await self._runtime["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="edit_medication",
            data_schema=self._build_medication_schema(
                profile_locked=False,
                profile_id=medication.profile_id,
                profile_name=medication.profile_name,
                medication_name=medication.name,
                dosage=medication.dosage,
                schedules=", ".join(medication.schedules),
                quantity="" if medication.quantity is None else str(medication.quantity),
                refill_at="" if medication.refill_at is None else str(medication.refill_at),
                notes=medication.notes,
                nfc_tag_id=medication.nfc_tag_id or "",
                notify_service=medication.notify_service or "",
                notification_enabled=medication.notification_enabled,
                reminder_minutes=medication.reminder_minutes,
                missed_after_minutes=medication.missed_after_minutes,
            ),
        )

    async def async_step_remove_medication_select(self, user_input=None):
        """Select a medication to remove."""
        medications = list(self._manager.list_medications())
        if not medications:
            return self.async_abort(reason="no_medications")

        if user_input is not None:
            await self._manager.async_remove_medication(user_input[ATTR_MEDICATION_ID])
            await self._runtime["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            return self.async_create_entry(title="", data={})

        options = {
            item.medication_id: f"{item.profile_name}: {item.name}"
            for item in medications
        }
        return self.async_show_form(
            step_id="remove_medication_select",
            data_schema=vol.Schema({vol.Required(ATTR_MEDICATION_ID): vol.In(options)}),
        )

    def _parse_schedules(self, raw_value):
        """Split a comma-separated schedule string."""
        return [item.strip() for item in str(raw_value).split(",") if item.strip()]

    def _coerce_optional_float(self, raw_value):
        """Convert an optional text field to float."""
        if raw_value in {"", None}:
            return None
        return float(raw_value)

    def _empty_to_none(self, raw_value):
        """Convert empty strings to None."""
        if raw_value in {"", None}:
            return None
        return raw_value

    def _slugify(self, value):
        """Create a simple slug without extra HA helpers."""
        return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())

    def _profiles(self):
        """Return known profiles keyed by profile_id."""
        profiles = {}
        for medication in self._manager.list_medications():
            profiles[medication.profile_id] = medication.profile_name
        return dict(sorted(profiles.items(), key=lambda item: item[1].lower()))

    def _notify_service_selector(self, default_value=""):
        """Return a selector for available notify services."""
        options = [selector.SelectOptionDict(value="", label="No mobile notification service")]
        for service_name in sorted(self.hass.services.async_services().get("notify", {})):
            if service_name == "notify":
                continue
            options.append(
                selector.SelectOptionDict(
                    value=f"notify.{service_name}",
                    label=f"notify.{service_name}",
                )
            )
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

    def _build_medication_schema(
        self,
        *,
        profile_locked,
        medication_name,
        dosage,
        schedules,
        quantity,
        refill_at,
        notes,
        nfc_tag_id,
        notify_service,
        notification_enabled,
        reminder_minutes,
        missed_after_minutes,
        profile_id="",
        profile_name="",
        medication_id="",
    ):
        """Build a user-friendly medication form."""
        schema = {}
        if not profile_locked:
            schema[vol.Required(ATTR_PROFILE_ID, default=profile_id)] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            )
            schema[vol.Required(ATTR_PROFILE_NAME, default=profile_name)] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            )

        schema[vol.Required(ATTR_MEDICATION_ID, default=medication_id)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        )
        schema[vol.Required(ATTR_MEDICATION_NAME, default=medication_name)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        )
        schema[vol.Required(ATTR_DOSAGE, default=dosage)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        )
        schema[vol.Required(ATTR_SCHEDULES, default=schedules)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        )
        schema[vol.Optional(ATTR_QUANTITY, default=quantity)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.NUMBER)
        )
        schema[vol.Optional(ATTR_REFILL_AT, default=refill_at)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.NUMBER)
        )
        schema[vol.Optional(ATTR_NOTES, default=notes)] = selector.TextSelector(
            selector.TextSelectorConfig(multiline=True, type=selector.TextSelectorType.TEXT)
        )
        schema[vol.Optional(ATTR_NFC_TAG_ID, default=nfc_tag_id)] = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        )
        schema[vol.Optional(ATTR_NOTIFY_SERVICE, default=notify_service)] = self._notify_service_selector(
            notify_service
        )
        schema[vol.Required(ATTR_NOTIFICATION_ENABLED, default=notification_enabled)] = selector.BooleanSelector()
        schema[vol.Required(ATTR_REMINDER_MINUTES, default=reminder_minutes)] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=240, step=1, mode=selector.NumberSelectorMode.BOX)
        )
        schema[
            vol.Required(ATTR_MISSED_AFTER_MINUTES, default=missed_after_minutes)
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=1440, step=1, mode=selector.NumberSelectorMode.BOX)
        )
        return vol.Schema(schema)
