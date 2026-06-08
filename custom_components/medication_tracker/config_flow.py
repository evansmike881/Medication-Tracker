"""Config flow for Medication Tracker."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN

CONF_DISPLAY_NAME = "name"


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
    """Minimal options flow to confirm handler loading."""

    def __init__(self, config_entry) -> None:
        """Store config entry."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Show a placeholder options form."""
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )
