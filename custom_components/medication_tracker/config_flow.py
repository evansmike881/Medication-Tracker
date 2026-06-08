"""Config flow for Medication Tracker."""

from __future__ import annotations

from datetime import time

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ATTR_DATABASE_ENTRY_ID,
    ATTR_DOSAGE,
    ATTR_MEDICATION_NAME,
    ATTR_MISSED_AFTER_MINUTES,
    ATTR_NFC_TAG_ID,
    ATTR_NOTES,
    ATTR_NOTIFICATION_ENABLED,
    ATTR_NOTIFY_SERVICE,
    ATTR_PROFILE_NAME,
    ATTR_QUANTITY,
    ATTR_REFILL_AT,
    ATTR_REMINDER_MINUTES,
    DEFAULT_MISSED_AFTER_MINUTES,
    DEFAULT_REMINDER_MINUTES,
    DOMAIN,
    SIGNAL_MEDICATIONS_UPDATED,
)

CONF_DISPLAY_NAME = "name"
CUSTOM_DATABASE_OPTION = "__custom__"
PROFILE_CHOICE = "profile_choice"
TIME_SLOT_KEYS = (
    "time_slot_1",
    "time_slot_2",
    "time_slot_3",
    "time_slot_4",
    "time_slot_5",
    "time_slot_6",
)


class MedicationTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Medication Tracker."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_DISPLAY_NAME], data={})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_DISPLAY_NAME, default="Medication Tracker"): str}
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
        self._draft: dict = {}

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
        self._reset_draft()
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
        self._reset_draft()
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
            profile_choice = user_input[PROFILE_CHOICE]
            if profile_choice == "__new__":
                return await self.async_step_add_medication_profile_new()
            self._selected_profile_id, self._selected_profile_name = profile_choice.split("|", 1)
            return await self.async_step_add_medication_basic()

        options = [selector.SelectOptionDict(value="__new__", label="Create a new person or pet")]
        options.extend(
            selector.SelectOptionDict(
                value=f"{profile_id}|{profile_name}",
                label=profile_name,
            )
            for profile_id, profile_name in profiles.items()
        )
        return self.async_show_form(
            step_id="add_medication_pick_profile",
            data_schema=vol.Schema(
                {
                    vol.Required(PROFILE_CHOICE, default="__new__"): selector.SelectSelector(
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
            self._selected_profile_name = user_input[ATTR_PROFILE_NAME]
            self._selected_profile_id = self._make_unique_profile_id(self._selected_profile_name)
            return await self.async_step_add_medication_basic()

        return self.async_show_form(
            step_id="add_medication_profile_new",
            data_schema=vol.Schema(
                {
                    vol.Required(ATTR_PROFILE_NAME): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                }
            ),
        )

    async def async_step_add_medication_basic(self, user_input=None):
        """Capture the basic medication details."""
        database_entry = None
        if self._selected_database_entry_id != CUSTOM_DATABASE_OPTION:
            database_entry = self._manager.get_database_entry(self._selected_database_entry_id)

        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_add_medication_schedule()

        return self.async_show_form(
            step_id="add_medication_basic",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        ATTR_MEDICATION_NAME,
                        default=database_entry["name"] if database_entry else "",
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        ATTR_DOSAGE,
                        default=database_entry["default_dosage"] if database_entry else "",
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Optional(
                        ATTR_NOTES,
                        default=database_entry["notes"] if database_entry else "",
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True, type=selector.TextSelectorType.TEXT)
                    ),
                }
            ),
        )

    async def async_step_add_medication_schedule(self, user_input=None):
        """Capture medication times using time pickers."""
        if user_input is not None:
            schedule_values = self._extract_schedule_values(user_input)
            if not schedule_values:
                return self.async_show_form(
                    step_id="add_medication_schedule",
                    data_schema=self._time_schema(),
                    errors={"base": "at_least_one_time"},
                )
            self._draft["schedules"] = schedule_values
            return await self.async_step_add_medication_advanced()

        return self.async_show_form(
            step_id="add_medication_schedule",
            data_schema=self._time_schema(),
        )

    async def async_step_add_medication_advanced(self, user_input=None):
        """Capture optional advanced settings and save the medication."""
        if user_input is not None:
            self._draft.update(user_input)
            await self._manager.async_add_medication(
                profile_id=self._selected_profile_id,
                profile_name=self._selected_profile_name,
                medication_id=self._make_unique_medication_id(self._draft[ATTR_MEDICATION_NAME]),
                medication_name=self._draft[ATTR_MEDICATION_NAME],
                dosage=self._draft[ATTR_DOSAGE],
                schedules=self._draft["schedules"],
                quantity=self._coerce_optional_float(self._draft.get(ATTR_QUANTITY)),
                refill_at=self._coerce_optional_float(self._draft.get(ATTR_REFILL_AT)),
                notes=self._draft.get(ATTR_NOTES, ""),
                database_entry_id=(
                    None
                    if self._selected_database_entry_id == CUSTOM_DATABASE_OPTION
                    else self._selected_database_entry_id
                ),
                nfc_tag_id=self._empty_to_none(self._draft.get(ATTR_NFC_TAG_ID)),
                notification_enabled=self._draft.get(ATTR_NOTIFICATION_ENABLED, True),
                notify_service=self._empty_to_none(self._draft.get(ATTR_NOTIFY_SERVICE)),
                reminder_minutes=int(self._draft.get(ATTR_REMINDER_MINUTES, DEFAULT_REMINDER_MINUTES)),
                missed_after_minutes=int(
                    self._draft.get(ATTR_MISSED_AFTER_MINUTES, DEFAULT_MISSED_AFTER_MINUTES)
                ),
            )
            await self._runtime["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            self._reset_draft()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add_medication_advanced",
            data_schema=self._advanced_schema(),
        )

    async def async_step_edit_medication_select(self, user_input=None):
        """Select a medication to edit."""
        medications = list(self._manager.list_medications())
        if not medications:
            return self.async_abort(reason="no_medications")

        if user_input is not None:
            self._selected_medication_id = user_input["selected_medication"]
            medication = self._manager.medications[self._selected_medication_id]
            self._selected_profile_id = medication.profile_id
            self._selected_profile_name = medication.profile_name
            self._draft = {
                ATTR_MEDICATION_NAME: medication.name,
                ATTR_DOSAGE: medication.dosage,
                ATTR_NOTES: medication.notes,
                "schedules": medication.schedules,
                ATTR_QUANTITY: "" if medication.quantity is None else str(medication.quantity),
                ATTR_REFILL_AT: "" if medication.refill_at is None else str(medication.refill_at),
                ATTR_NFC_TAG_ID: medication.nfc_tag_id or "",
                ATTR_NOTIFY_SERVICE: medication.notify_service or "",
                ATTR_NOTIFICATION_ENABLED: medication.notification_enabled,
                ATTR_REMINDER_MINUTES: medication.reminder_minutes,
                ATTR_MISSED_AFTER_MINUTES: medication.missed_after_minutes,
            }
            return await self.async_step_edit_medication_basic()

        options = [
            selector.SelectOptionDict(
                value=item.medication_id,
                label=f"{item.profile_name}: {item.name}",
            )
            for item in medications
        ]
        return self.async_show_form(
            step_id="edit_medication_select",
            data_schema=vol.Schema(
                {
                    vol.Required("selected_medication"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_edit_medication_basic(self, user_input=None):
        """Edit basic medication details."""
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_edit_medication_schedule()

        return self.async_show_form(
            step_id="edit_medication_basic",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        ATTR_PROFILE_NAME,
                        default=self._selected_profile_name,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        ATTR_MEDICATION_NAME,
                        default=self._draft[ATTR_MEDICATION_NAME],
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Required(
                        ATTR_DOSAGE,
                        default=self._draft[ATTR_DOSAGE],
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    ),
                    vol.Optional(
                        ATTR_NOTES,
                        default=self._draft.get(ATTR_NOTES, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True, type=selector.TextSelectorType.TEXT)
                    ),
                }
            ),
        )

    async def async_step_edit_medication_schedule(self, user_input=None):
        """Edit schedule times."""
        if user_input is not None:
            schedule_values = self._extract_schedule_values(user_input)
            if not schedule_values:
                return self.async_show_form(
                    step_id="edit_medication_schedule",
                    data_schema=self._time_schema(self._draft.get("schedules", [])),
                    errors={"base": "at_least_one_time"},
                )
            self._draft["schedules"] = schedule_values
            return await self.async_step_edit_medication_advanced()

        return self.async_show_form(
            step_id="edit_medication_schedule",
            data_schema=self._time_schema(self._draft.get("schedules", [])),
        )

    async def async_step_edit_medication_advanced(self, user_input=None):
        """Edit advanced settings and save."""
        medication = self._manager.medications[self._selected_medication_id]
        if user_input is not None:
            self._draft.update(user_input)
            await self._manager.async_add_medication(
                profile_id=medication.profile_id,
                profile_name=self._draft[ATTR_PROFILE_NAME],
                medication_id=medication.medication_id,
                medication_name=self._draft[ATTR_MEDICATION_NAME],
                dosage=self._draft[ATTR_DOSAGE],
                schedules=self._draft["schedules"],
                quantity=self._coerce_optional_float(self._draft.get(ATTR_QUANTITY)),
                refill_at=self._coerce_optional_float(self._draft.get(ATTR_REFILL_AT)),
                notes=self._draft.get(ATTR_NOTES, ""),
                database_entry_id=medication.database_entry_id,
                nfc_tag_id=self._empty_to_none(self._draft.get(ATTR_NFC_TAG_ID)),
                notification_enabled=self._draft.get(ATTR_NOTIFICATION_ENABLED, True),
                notify_service=self._empty_to_none(self._draft.get(ATTR_NOTIFY_SERVICE)),
                reminder_minutes=int(self._draft.get(ATTR_REMINDER_MINUTES, medication.reminder_minutes)),
                missed_after_minutes=int(
                    self._draft.get(ATTR_MISSED_AFTER_MINUTES, medication.missed_after_minutes)
                ),
            )
            await self._runtime["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            self._reset_draft()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="edit_medication_advanced",
            data_schema=self._advanced_schema(
                quantity=self._draft.get(ATTR_QUANTITY, ""),
                refill_at=self._draft.get(ATTR_REFILL_AT, ""),
                nfc_tag_id=self._draft.get(ATTR_NFC_TAG_ID, ""),
                notify_service=self._draft.get(ATTR_NOTIFY_SERVICE, ""),
                notification_enabled=self._draft.get(ATTR_NOTIFICATION_ENABLED, True),
                reminder_minutes=self._draft.get(ATTR_REMINDER_MINUTES, DEFAULT_REMINDER_MINUTES),
                missed_after_minutes=self._draft.get(
                    ATTR_MISSED_AFTER_MINUTES, DEFAULT_MISSED_AFTER_MINUTES
                ),
            ),
        )

    async def async_step_remove_medication_select(self, user_input=None):
        """Select a medication to remove."""
        medications = list(self._manager.list_medications())
        if not medications:
            return self.async_abort(reason="no_medications")

        if user_input is not None:
            await self._manager.async_remove_medication(user_input["selected_medication"])
            await self._runtime["coordinator"].async_request_refresh()
            async_dispatcher_send(self.hass, SIGNAL_MEDICATIONS_UPDATED)
            self._reset_draft()
            return self.async_create_entry(title="", data={})

        options = [
            selector.SelectOptionDict(
                value=item.medication_id,
                label=f"{item.profile_name}: {item.name}",
            )
            for item in medications
        ]
        return self.async_show_form(
            step_id="remove_medication_select",
            data_schema=vol.Schema(
                {
                    vol.Required("selected_medication"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    def _profiles(self):
        """Return known profiles keyed by profile_id."""
        profiles = {}
        for medication in self._manager.list_medications():
            profiles[medication.profile_id] = medication.profile_name
        return dict(sorted(profiles.items(), key=lambda item: item[1].lower()))

    def _advanced_schema(
        self,
        *,
        quantity="",
        refill_at="",
        nfc_tag_id="",
        notify_service="",
        notification_enabled=True,
        reminder_minutes=DEFAULT_REMINDER_MINUTES,
        missed_after_minutes=DEFAULT_MISSED_AFTER_MINUTES,
    ):
        """Build the advanced settings form."""
        return vol.Schema(
            {
                vol.Optional(ATTR_QUANTITY, default=quantity): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.NUMBER)
                ),
                vol.Optional(ATTR_REFILL_AT, default=refill_at): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.NUMBER)
                ),
                vol.Optional(ATTR_NFC_TAG_ID, default=nfc_tag_id): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(ATTR_NOTIFY_SERVICE, default=notify_service): self._notify_service_selector(),
                vol.Required(ATTR_NOTIFICATION_ENABLED, default=notification_enabled): selector.BooleanSelector(),
                vol.Required(ATTR_REMINDER_MINUTES, default=reminder_minutes): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=240,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(ATTR_MISSED_AFTER_MINUTES, default=missed_after_minutes): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=1440,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

    def _time_schema(self, schedules=None):
        """Build the schedule form with multiple time pickers."""
        schedules = schedules or []
        schedule_defaults = []
        for item in schedules:
            parsed = time.fromisoformat(item)
            schedule_defaults.append(parsed)
        while len(schedule_defaults) < len(TIME_SLOT_KEYS):
            schedule_defaults.append(None)

        schema: dict = {}
        for index, key in enumerate(TIME_SLOT_KEYS):
            validator = vol.Required if index == 0 else vol.Optional
            schema[validator(key, default=schedule_defaults[index])] = selector.TimeSelector()
        return vol.Schema(schema)

    def _extract_schedule_values(self, user_input):
        """Extract and normalize schedule times from the form."""
        schedules = []
        for key in TIME_SLOT_KEYS:
            value = user_input.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, time):
                schedules.append(value.strftime("%H:%M"))
            else:
                schedules.append(str(value)[:5])
        return schedules

    def _notify_service_selector(self):
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

    def _make_unique_profile_id(self, profile_name):
        """Create a unique profile ID from a friendly name."""
        return self._make_unique_slug(profile_name, set(self._profiles()))

    def _make_unique_medication_id(self, medication_name):
        """Create a unique medication ID from a medication name."""
        return self._make_unique_slug(medication_name, set(self._manager.medications))

    def _make_unique_slug(self, value, existing_ids):
        """Create a unique slug and add a suffix when needed."""
        base = self._slugify(value) or "item"
        candidate = base
        suffix = 2
        while candidate in existing_ids:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def _reset_draft(self):
        """Reset flow state."""
        self._selected_database_entry_id = CUSTOM_DATABASE_OPTION
        self._selected_medication_id = None
        self._selected_profile_id = None
        self._selected_profile_name = None
        self._draft = {}
