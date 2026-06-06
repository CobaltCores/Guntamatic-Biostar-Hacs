"""The GuntamaticBiostar component - Dynamic binary sensor creation based on API response."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BiostarUpdateCoordinator
from .const import (
    DOMAIN,
    get_icon_for_key,
    should_exclude_key,
)
from .entity_helpers import device_info_for_entry, dynamic_entity_unique_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors dynamically based on API data."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known_keys: set[str] = set()

    @callback
    def async_add_new_entities() -> None:
        """Add new binary sensors discovered from coordinator data."""
        sensors = []
        for key, value_data in coordinator.data.items():
            if key in known_keys or should_exclude_key(key):
                continue

            if _is_boolean(value_data):
                known_keys.add(key)
                sensors.append(
                    GuntamaticDynamicBinarySensor(
                        coordinator=coordinator,
                        sensor_key=key,
                    )
                )

        if sensors:
            _LOGGER.debug("Created %s binary sensors from API data", len(sensors))
            async_add_entities(sensors)

    async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_entities))


def _is_boolean(value_data) -> bool:
    """Return true if an API value should be represented as a binary sensor."""
    if isinstance(value_data, (list, tuple)) and value_data:
        return isinstance(value_data[0], bool)
    return isinstance(value_data, bool)


class GuntamaticDynamicBinarySensor(
    CoordinatorEntity[BiostarUpdateCoordinator], BinarySensorEntity
):
    """A dynamically created binary sensor based on API data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BiostarUpdateCoordinator,
        sensor_key: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._sensor_key = sensor_key

        # Clean the key name (remove leading underscore from status.cgi keys)
        display_name = sensor_key.lstrip("_")

        self._attr_unique_id = dynamic_entity_unique_id(
            coordinator.config_entry,
            sensor_key,
        )

        # Set the name
        self._attr_name = display_name

        # Set icon based on key patterns
        self._attr_icon = get_icon_for_key(sensor_key)

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        sensor_data = self.coordinator.data.get(self._sensor_key)
        if sensor_data is None:
            return None
        if isinstance(sensor_data, (list, tuple)) and len(sensor_data) > 0:
            return sensor_data[0]
        return sensor_data

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return device_info_for_entry(
            self.coordinator.config_entry,
            self.coordinator.get_device_info(),
        )
