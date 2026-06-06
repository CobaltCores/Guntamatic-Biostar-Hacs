"""Select platform for Guntamatic Biostar program control."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BiostarUpdateCoordinator
from .const import (
    DOMAIN,
    PROGRAM_OPTIONS,
    is_program_state_key,
    normalize_program_option,
)
from .entity_helpers import config_entry_unique_id, device_info_for_entry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Guntamatic Biostar select entities."""
    coordinator: BiostarUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Only add program select if write access is available
    if coordinator.has_write_access():
        async_add_entities([GuntamaticProgramSelect(coordinator)])
        _LOGGER.info("Write access available - Program select entity added")
    else:
        _LOGGER.debug("No write key configured - Skipping program select entity")


class GuntamaticProgramSelect(CoordinatorEntity, SelectEntity):
    """Select entity for heating program control."""

    _attr_has_entity_name = True
    _attr_translation_key = "heating_program"
    _attr_icon = "mdi:thermostat"

    def __init__(self, coordinator: BiostarUpdateCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{config_entry_unique_id(coordinator.config_entry)}_program"
        )
        self._attr_options = list(PROGRAM_OPTIONS.keys())

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return device_info_for_entry(
            self.coordinator.config_entry,
            self.coordinator.get_device_info(),
        )

    @property
    def current_option(self) -> str | None:
        """Return current selected option."""
        # Try to get current program from coordinator data
        data = self.coordinator.data
        if data:
            for key, raw_value in data.items():
                if not is_program_state_key(key):
                    continue

                value = raw_value[0] if isinstance(raw_value, list) else raw_value
                if option := normalize_program_option(value):
                    return option
        # Default to None if no state found (shows as Unknown in UI)
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in PROGRAM_OPTIONS:
            _LOGGER.error(f"Invalid program option: {option}")
            return

        program_id = PROGRAM_OPTIONS[option]
        _LOGGER.info(f"Setting heating program to: {option} (ID: {program_id})")

        success = await self.coordinator.async_set_program(program_id)

        if not success:
            _LOGGER.error(f"Failed to set program to {option}")
