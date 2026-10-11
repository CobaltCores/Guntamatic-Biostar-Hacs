"""Data update coordinator for the Guntamatic Biostar integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BiostarClient, BiostarCommandError, BiostarData, BiostarError
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS
from .entity_helpers import config_entry_unique_id

_LOGGER = logging.getLogger(__name__)

type BiostarConfigEntry = ConfigEntry[BiostarCoordinator]


class BiostarCoordinator(DataUpdateCoordinator[BiostarData]):
    """Poll the boiler and run write commands."""

    config_entry: BiostarConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: BiostarConfigEntry,
        client: BiostarClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client

    @property
    def entry_unique_id(self) -> str:
        """Return the prefix used for unique IDs of this boiler."""
        return config_entry_unique_id(self.config_entry)

    async def _async_update_data(self) -> BiostarData:
        try:
            async with asyncio.timeout(30):
                return await self.client.async_get_data()
        except BiostarError as err:
            raise UpdateFailed(str(err)) from err
        except TimeoutError as err:
            raise UpdateFailed("Timeout while polling the boiler") from err

    async def async_command(
        self,
        command: Awaitable[None],
        description: str,
        applied: Callable[[BiostarData], bool] | None = None,
    ) -> None:
        """Run a write command, surface failures in the UI and refresh.

        ``applied`` checks the next poll; a boiler that acknowledges a value
        and then reports something else is logged, since parameter tables
        may differ between models and firmware versions.
        """
        try:
            await command
        except BiostarCommandError as err:
            raise HomeAssistantError(str(err)) from err
        await self.async_refresh()
        if applied is not None and self.last_update_success and not applied(self.data):
            _LOGGER.warning(
                "The boiler acknowledged %s but does not report it after the next "
                "poll. If this persists, please open an issue with your boiler "
                "model and firmware version",
                description,
            )
