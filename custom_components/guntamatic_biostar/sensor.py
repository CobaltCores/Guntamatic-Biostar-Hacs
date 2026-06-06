"""The GuntamaticBiostar component - Dynamic sensor creation based on API response."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BiostarUpdateCoordinator
from .const import (
    DOMAIN,
    get_sensor_metadata,
    get_icon_for_key,
    is_diagnostic_sensor,
    should_exclude_key,
)
from .entity_helpers import device_info_for_entry, dynamic_entity_unique_id

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors dynamically based on API data."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known_keys: set[str] = set()

    @callback
    def async_add_new_entities() -> None:
        """Add new sensors discovered from coordinator data."""
        sensors = []
        for key, value_data in coordinator.data.items():
            if key in known_keys or should_exclude_key(key) or _is_boolean(value_data):
                continue

            known_keys.add(key)
            sensors.append(
                GuntamaticDynamicSensor(
                    coordinator=coordinator,
                    sensor_key=key,
                    sensor_unit=_get_unit(value_data),
                )
            )

        if sensors:
            _LOGGER.debug("Created %s sensors from API data", len(sensors))
            async_add_entities(sensors)

    async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_entities))


def _get_unit(value_data) -> str | None:
    """Return the unit from an API value tuple/list."""
    if isinstance(value_data, (list, tuple)) and len(value_data) > 1:
        return value_data[1]
    return None


def _is_boolean(value_data) -> bool:
    """Return true if an API value should be represented as a binary sensor."""
    if isinstance(value_data, (list, tuple)) and value_data:
        return isinstance(value_data[0], bool)
    return isinstance(value_data, bool)


class GuntamaticDynamicSensor(
    CoordinatorEntity[BiostarUpdateCoordinator], SensorEntity
):
    """A dynamically created sensor based on API data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BiostarUpdateCoordinator,
        sensor_key: str,
        sensor_unit: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator=coordinator)

        self._sensor_key = sensor_key
        self._sensor_unit = sensor_unit

        # Clean the key name (remove leading underscore from status.cgi keys)
        display_name = sensor_key.lstrip("_")

        self._attr_unique_id = dynamic_entity_unique_id(
            coordinator.config_entry,
            sensor_key,
        )

        # Set the name (will be combined with device name: "Guntamatic Biostar Température chaudière")
        self._attr_name = display_name

        # Set icon based on key patterns
        self._attr_icon = get_icon_for_key(sensor_key)

        # Set as diagnostic if applicable
        if is_diagnostic_sensor(sensor_key):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Set device class and unit based on the unit from API
        mapping = get_sensor_metadata(sensor_key, sensor_unit)
        if mapping:
            self._attr_device_class = mapping["device_class"]
            self._attr_native_unit_of_measurement = mapping["unit"]
            self._attr_state_class = mapping["state_class"]
        else:
            # No unit or unknown unit - text sensor
            self._attr_device_class = None
            self._attr_native_unit_of_measurement = None
            self._attr_state_class = None

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
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
