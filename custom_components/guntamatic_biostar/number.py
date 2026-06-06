"""Number platform for Guntamatic Biostar temperature control."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BiostarUpdateCoordinator
from .const import DOMAIN
from .entity_helpers import config_entry_unique_id, device_info_for_entry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Guntamatic Biostar number entities."""
    coordinator: BiostarUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Only add number entities if write access is available
    if not coordinator.has_write_access():
        _LOGGER.debug("No write key configured - Skipping number entities")
        return

    # Wait for data to be available
    if not coordinator.data:
        await coordinator.async_refresh()

    # Get heating circuits and create entities for each
    heating_circuits = coordinator.get_heating_circuits()
    constraints = coordinator.get_heat_constraints()

    entities = []
    for circuit in heating_circuits:
        circuit_nr = int(circuit.get("nr", 0))
        circuit_name = circuit.get("name", f"Circuit {circuit_nr}")

        # Day temperature
        entities.append(
            GuntamaticTempNumber(
                coordinator=coordinator,
                circuit_nr=circuit_nr,
                circuit_name=circuit_name,
                temp_type="day",
                constraints=constraints,
            )
        )

        # Night temperature
        entities.append(
            GuntamaticTempNumber(
                coordinator=coordinator,
                circuit_nr=circuit_nr,
                circuit_name=circuit_name,
                temp_type="night",
                constraints=constraints,
            )
        )

    if entities:
        async_add_entities(entities)
        _LOGGER.info(f"Added {len(entities)} temperature control entities")
    else:
        _LOGGER.debug("No heating circuits found - No temperature entities created")


class GuntamaticTempNumber(CoordinatorEntity, NumberEntity):
    """Number entity for heating circuit temperature control."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: BiostarUpdateCoordinator,
        circuit_nr: int,
        circuit_name: str,
        temp_type: str,
        constraints: dict,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._circuit_nr = circuit_nr
        self._circuit_name = circuit_name
        self._temp_type = temp_type

        # Translation key will be 'day_temperature' or 'night_temperature'
        self._attr_translation_key = f"{temp_type}_temperature"

        # Unique ID
        self._attr_unique_id = f"{config_entry_unique_id(coordinator.config_entry)}_{circuit_nr}_{temp_type}_temp"

        # Temperature constraints from API
        self._attr_native_min_value = constraints.get("min", 15.0)
        self._attr_native_max_value = constraints.get("max", 30.0)
        self._attr_native_step = constraints.get("inc", 0.5)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return device_info_for_entry(
            self.coordinator.config_entry,
            self.coordinator.get_device_info(),
        )

    @property
    def native_value(self) -> float | None:
        """Return the current temperature value."""
        heating_circuits = self.coordinator.get_heating_circuits()

        for circuit in heating_circuits:
            if int(circuit.get("nr", 0)) == self._circuit_nr:
                if self._temp_type == "day":
                    return circuit.get("day_temp")
                else:
                    return circuit.get("night_temp")

        return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the temperature value."""
        _LOGGER.info(
            f"Setting {self._temp_type} temperature to {value}°C for {self._circuit_name}"
        )

        success = await self.coordinator.async_set_temperature(
            self._circuit_nr, self._temp_type, value
        )

        if not success:
            _LOGGER.error(
                f"Failed to set {self._temp_type} temperature for {self._circuit_name}"
            )
