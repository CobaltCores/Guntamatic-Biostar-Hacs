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
from homeassistant.util import slugify

from . import BiostarUpdateCoordinator
from .const import (
    DOMAIN,
    MANUFACTURER,
    UNIT_DEVICE_CLASS_MAP,
    get_icon_for_key,
    is_diagnostic_sensor,
    should_exclude_key,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors dynamically based on API data."""
    coordinator = hass.data[DOMAIN][config.entry_id]

    sensors = []

    # Create sensors dynamically from the coordinator data
    if coordinator.data:
        for key, value_data in coordinator.data.items():
            # Skip excluded keys (reserved, etc.)
            if should_exclude_key(key):
                continue

            # Get unit from API data
            unit = None
            if isinstance(value_data, (list, tuple)) and len(value_data) > 1:
                unit = value_data[1]

            # Skip boolean values - they will be handled by binary_sensor
            if isinstance(value_data, (list, tuple)) and len(value_data) > 0:
                if isinstance(value_data[0], bool):
                    continue

            sensors.append(
                GuntamaticDynamicSensor(
                    coordinator=coordinator,
                    sensor_key=key,
                    sensor_unit=unit,
                )
            )

    _LOGGER.info(f"Created {len(sensors)} sensors from API data")
    async_add_entities(sensors)


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
        self._sensor_data = coordinator.data

        # Clean the key name (remove leading underscore from status.cgi keys)
        display_name = sensor_key.lstrip("_")

        # Use a clean unique ID based only on the sensor key
        self._attr_unique_id = f"biostar_{slugify(sensor_key)}"

        # Set the name (will be combined with device name: "Guntamatic Biostar Température chaudière")
        self._attr_name = display_name

        # Set icon based on key patterns
        self._attr_icon = get_icon_for_key(sensor_key)

        # Set as diagnostic if applicable
        if is_diagnostic_sensor(sensor_key):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Set device class and unit based on the unit from API
        if sensor_unit and sensor_unit in UNIT_DEVICE_CLASS_MAP:
            mapping = UNIT_DEVICE_CLASS_MAP[sensor_unit]
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
        sensor_data = self._sensor_data.get(self._sensor_key)
        if sensor_data is None:
            return None

        if isinstance(sensor_data, (list, tuple)) and len(sensor_data) > 0:
            return sensor_data[0]
        return sensor_data

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        # Try to get device info from API
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
