"""Config flow for the Guntamatic Biostar integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BiostarClient, BiostarError
from .const import (
    CONF_INCLUDE_LEGACY,
    CONFIG_ENTRY_VERSION,
    DATA_SCHEMA,
    DATA_SCHEMA_API_KEY,
    DATA_SCHEMA_HOST,
    DEFAULT_INCLUDE_LEGACY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class GuntamaticBiostarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Guntamatic Biostar boiler."""

    VERSION = CONFIG_ENTRY_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return GuntamaticBiostarOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host and keys, then check the boiler answers."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[DATA_SCHEMA_HOST].strip()
            user_input[DATA_SCHEMA_HOST] = host
            self._async_abort_entries_match({DATA_SCHEMA_HOST: host})

            client = BiostarClient(
                session=async_get_clientsession(self.hass),
                host=host,
                api_key=user_input[DATA_SCHEMA_API_KEY],
            )
            try:
                unique_id = await client.async_get_unique_id()
            except BiostarError as err:
                _LOGGER.debug("Connection test to %s failed: %s", host, err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(
                    title=f"Guntamatic Biostar ({host})",
                    data=user_input,
                    options={CONF_INCLUDE_LEGACY: DEFAULT_INCLUDE_LEGACY},
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class GuntamaticBiostarOptionsFlow(OptionsFlow):
    """Options for Guntamatic Biostar."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INCLUDE_LEGACY,
                        default=self.config_entry.options.get(
                            CONF_INCLUDE_LEGACY, DEFAULT_INCLUDE_LEGACY
                        ),
                    ): bool,
                }
            ),
        )
