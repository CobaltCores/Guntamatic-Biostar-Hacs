"""Guntamatic Biostar integration for Home Assistant."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BiostarClient
from .const import (
    CONF_INCLUDE_LEGACY,
    CONFIG_ENTRY_VERSION,
    DATA_SCHEMA_API_KEY,
    DATA_SCHEMA_HOST,
    DATA_SCHEMA_WRITE_KEY,
    DEFAULT_INCLUDE_LEGACY,
    PLATFORMS,
)
from .coordinator import BiostarConfigEntry, BiostarCoordinator
from .migration import migrate_v1_to_v2, migrate_v2_to_v3


async def async_setup_entry(hass: HomeAssistant, entry: BiostarConfigEntry) -> bool:
    """Set up Guntamatic Biostar from a config entry."""
    client = BiostarClient(
        session=async_get_clientsession(hass),
        host=entry.data[DATA_SCHEMA_HOST],
        api_key=entry.data[DATA_SCHEMA_API_KEY],
        write_key=entry.data.get(DATA_SCHEMA_WRITE_KEY),
        include_legacy=entry.options.get(CONF_INCLUDE_LEGACY, DEFAULT_INCLUDE_LEGACY),
    )
    coordinator = BiostarCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BiostarConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_options(hass: HomeAssistant, entry: BiostarConfigEntry) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: BiostarConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version > CONFIG_ENTRY_VERSION:
        return False

    if entry.version == 1:
        migrate_v1_to_v2(hass, entry)
        hass.config_entries.async_update_entry(entry, version=2)

    if entry.version == 2:
        migrate_v2_to_v3(hass, entry)
        hass.config_entries.async_update_entry(entry, version=3)

    return True
