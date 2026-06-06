"""The GuntamaticBiostar component for controlling the Guntamatic Biostar heating via home assistant / API"""

from __future__ import annotations

import logging
import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Import global values.
from .const import (
    CONF_INCLUDE_LEGACY,
    DATA_SCHEMA,
    DATA_SCHEMA_HOST,
    DATA_SCHEMA_API_KEY,
    DEFAULT_INCLUDE_LEGACY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class GuntamaticBiostarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuration flow for the configuration of the GuntamaticBiostar integration."""

    VERSION = 2

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "GuntamaticBiostarOptionsFlow":
        """Create the options flow."""
        return GuntamaticBiostarOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Test connection to the Biostar
            host = user_input[DATA_SCHEMA_HOST]
            api_key = user_input[DATA_SCHEMA_API_KEY]

            if self._host_already_configured(host):
                return self.async_abort(reason="already_configured")

            connection_info = await self._test_connection(host, api_key)

            if connection_info:
                await self.async_set_unique_id(connection_info["unique_id"])
                self._abort_if_unique_id_configured(
                    updates=user_input,
                )

                return self.async_create_entry(
                    title=f"Guntamatic Biostar ({host})",
                    data=user_input,
                    options={CONF_INCLUDE_LEGACY: DEFAULT_INCLUDE_LEGACY},
                )
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    def _host_already_configured(self, host: str) -> bool:
        """Return true if a config entry already uses this host."""
        host = host.strip().lower()
        for entry in self._async_current_entries():
            entry_host = str(entry.data.get(DATA_SCHEMA_HOST, "")).strip().lower()
            if entry_host == host:
                return True
        return False

    async def _test_connection(self, host: str, api_key: str) -> dict | None:
        """Test if we can connect to the Guntamatic Biostar."""
        session = async_get_clientsession(self.hass)
        params = {"key": api_key}

        # 1. Try modern JSON API first (/status.cgi)
        try:
            async with session.get(
                f"http://{host}/status.cgi",
                params=params,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    try:
                        # Validate it returns JSON
                        data = await resp.json(content_type=None)
                        if not isinstance(data, dict):
                            return None

                        meta = data.get("meta")
                        serial = meta.get("sn") if isinstance(meta, dict) else None
                        unique_id = str(serial or "").strip() or host
                        _LOGGER.debug(
                            f"Successfully connected to Guntamatic Biostar (JSON API) at {host}"
                        )
                        return {"unique_id": unique_id}
                    except Exception:
                        _LOGGER.debug(f"{host}/status.cgi did not return valid JSON")
        except Exception:
            _LOGGER.debug("%s/status.cgi connection test failed", host)

        # 2. Fallback to legacy API (/daqdesc.cgi)
        try:
            async with session.get(
                f"http://{host}/daqdesc.cgi",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    _LOGGER.debug(
                        f"Successfully connected to Guntamatic Biostar (Legacy API) at {host}"
                    )
                    return {"unique_id": host}
                else:
                    _LOGGER.warning(f"Connection test failed with status {resp.status}")
                    return None
        except aiohttp.ClientError as e:
            _LOGGER.warning(f"Connection test failed: {e}")
            return None
        except Exception as e:
            _LOGGER.error(f"Unexpected error during connection test: {e}")
            return None


class GuntamaticBiostarOptionsFlow(OptionsFlow):
    """Options flow for Guntamatic Biostar."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INCLUDE_LEGACY,
                        default=self._config_entry.options.get(
                            CONF_INCLUDE_LEGACY,
                            DEFAULT_INCLUDE_LEGACY,
                        ),
                    ): bool,
                }
            ),
        )
