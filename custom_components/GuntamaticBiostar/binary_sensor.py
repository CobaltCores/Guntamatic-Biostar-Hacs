"""The GuntamaticBiostar component - Dynamic binary sensor creation based on API response."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import BiostarUpdateCoordinator
from .const import (
    DOMAIN,
    MANUFACTURER,
    get_icon_for_key,
    should_exclude_key,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors dynamically based on API data."""
    coordinator = hass.data[DOMAIN][config.entry_id]

    sensors = []

    # Create binary sensors dynamically from the coordinator data
    if coordinator.data:
        for key, value_data in coordinator.data.items():
            # Skip excluded keys (reserved, etc.)
            if should_exclude_key(key):
                continue

            # Only create binary sensor for boolean values
            is_boolean = False
            if isinstance(value_data, (list, tuple)) and len(value_data) > 0:
                if isinstance(value_data[0], bool):
                    is_boolean = True
            elif isinstance(value_data, bool):
                is_boolean = True

            if is_boolean:
                sensors.append(
                    GuntamaticDynamicBinarySensor(
                        coordinator=coordinator,
                        sensor_key=key,
                    )
                )

    _LOGGER.info(f"Created {len(sensors)} binary sensors from API data")
    async_add_entities(sensors)


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
        self._sensor_data = coordinator.data

        # Clean the key name (remove leading underscore from status.cgi keys)
        display_name = sensor_key.lstrip("_")

        # Use a clean unique ID based only on the sensor key
        self._attr_unique_id = f"biostar_{slugify(sensor_key)}"

        # Set the name
        self._attr_name = display_name

        # Set icon based on key patterns
        self._attr_icon = get_icon_for_key(sensor_key)

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        sensor_data = self._sensor_data.get(self._sensor_key)
        if sensor_data is None:
            return None
        if isinstance(sensor_data, (list, tuple)) and len(sensor_data) > 0:
            return sensor_data[0]
        return sensor_data

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        api_device_info = self.coordinator.get_device_info()

        model = "Biostar"
        sw_version = None
        serial = None

        if api_device_info:
            model = api_device_info.get("typ", "Biostar")
            sw_version = api_device_info.get("sw_version")
            serial = api_device_info.get("sn")

        return DeviceInfo(
            identifiers={(DOMAIN, "biostar")},
            name="Guntamatic Biostar",
            manufacturer=MANUFACTURER,
            model=model,
            sw_version=sw_version,
            serial_number=serial,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        self._sensor_data = self.coordinator.data
        self.async_write_ha_state()
