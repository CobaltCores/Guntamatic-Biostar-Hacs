"""The GuntamaticBiostar component for controlling the Guntamatic Biostar heating via home assistant / API"""

from __future__ import annotations

import logging
import aiohttp

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Import global values.
from .const import DATA_SCHEMA, DATA_SCHEMA_HOST, DATA_SCHEMA_API_KEY, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GuntamaticBiostarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configuration flow for the configuration of the GuntamaticBiostar integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Test connection to the Biostar
            host = user_input[DATA_SCHEMA_HOST]
            api_key = user_input[DATA_SCHEMA_API_KEY]

            can_connect = await self._test_connection(host, api_key)

            if can_connect:
                # Set unique ID based on host to allow multiple devices
                await self.async_set_unique_id(f"{DOMAIN}_{host}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Guntamatic Biostar ({host})",
                    data=user_input,
                )
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, host: str, api_key: str) -> bool:
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
                        await resp.json(content_type=None)
                        _LOGGER.debug(
                            f"Successfully connected to Guntamatic Biostar (JSON API) at {host}"
                        )
                        return True
                    except Exception:
                        _LOGGER.debug(f"{host}/status.cgi did not return valid JSON")
        except Exception:
            pass

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
                    return True
                else:
                    _LOGGER.warning(f"Connection test failed with status {resp.status}")
                    return False
        except aiohttp.ClientError as e:
            _LOGGER.warning(f"Connection test failed: {e}")
            return False
        except Exception as e:
            _LOGGER.error(f"Unexpected error during connection test: {e}")
            return False
