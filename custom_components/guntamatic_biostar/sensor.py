"""Sensors for the Guntamatic Biostar integration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from guntamatic.heater import TRANSLATE
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import slugify

from .api import NUMERIC_UNITS
from .coordinator import BiostarConfigEntry, BiostarCoordinator
from .entity import BiostarEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class KeySpec:
    """How to present one stable data key."""

    translation_key: str
    diagnostic: bool = False
    enabled_default: bool = True
    state_class: SensorStateClass | None = None


DIAG = {"diagnostic": True}

# (pattern, translation key, options). A pattern group, when present, is the
# slot number and becomes the {index} placeholder of the translated name.
KEY_SPECS: list[tuple[str, str, dict[str, Any]]] = [
    (r"boiler_temperature", "boiler_temperature", {}),
    (r"outdoor_temperature", "outdoor_temperature", {}),
    (r"buffer_load", "buffer_load", {}),
    (r"buffer_top_temperature", "buffer_top_temperature", {}),
    (r"buffer_center_temperature", "buffer_center_temperature", {}),
    (r"buffer_bottom_temperature", "buffer_bottom_temperature", {}),
    (r"buffer_top_(\d+)_temperature", "buffer_top_n_temperature", {}),
    (r"buffer_bottom_(\d+)_temperature", "buffer_bottom_n_temperature", {}),
    (r"buffer_t(\d+)_temperature", "buffer_tn_temperature", {}),
    (r"domestic_hot_water_(\d+)_temperature", "dhw_temperature", {}),
    (r"extra_dhw_(\d+)_temperature", "extra_dhw_temperature", {}),
    (r"extra_dhw_boost_(\d+)", "extra_dhw_boost", DIAG),
    (r"dhw_pump_(\d+)", "dhw_pump", DIAG),
    (r"room_(\d+)_temperature", "room_temperature", {}),
    (r"circuit_(\d+)_temp", "flow_temperature", {}),
    (r"heating_circulation_pump_(\d+)", "circuit_pump", DIAG),
    (r"heating_circulation_program_(\d+)", "circuit_program", {}),
    (r"auxiliary_pump_(\d+)", "auxiliary_pump", DIAG),
    (r"heating_circuit_(\d+)_day_target", "circuit_day_target", {}),
    (r"heating_circuit_(\d+)_night_target", "circuit_night_target", {}),
    (r"boiler_shunt_pump", "boiler_shunt_pump", DIAG),
    (r"suction_fan", "suction_fan", DIAG),
    (r"primary_air", "primary_air", DIAG),
    (r"secondary_air", "secondary_air", DIAG),
    (r"discharge_motor", "discharge_motor", DIAG),
    (r"grate", "grate", DIAG),
    (r"g1_target", "g1_target", DIAG),
    (r"output", "output", {}),
    (r"co2_content", "co2_content", {}),
    (r"flue_gas", "flue_gas", {}),
    (r"fuel_level", "fuel_level", {}),
    (r"program", "program", {}),
    (r"status", "status", {}),
    (r"interruption_(\d+)", "fault_message", DIAG),
    (
        r"operating_time",
        "operating_time",
        {"diagnostic": True, "state_class": SensorStateClass.TOTAL_INCREASING},
    ),
    (r"service_hours", "service_hours", DIAG),
    (r"service_days", "service_days", {"diagnostic": True, "enabled_default": False}),
    (r"ash_empty_in", "ash_empty_in", {}),
    (r"cleaning_countdown", "cleaning_countdown", {}),
    (r"serial", "serial", DIAG),
    (r"version", "version", DIAG),
    (r"last_update", "last_update", {"diagnostic": True, "enabled_default": False}),
]
_COMPILED = [
    (re.compile(rf"^{pattern}$"), key, opts) for pattern, key, opts in KEY_SPECS
]
LIBRARY_KEYS = set(TRANSLATE.values())

UNIT_METADATA: dict[str, tuple[SensorDeviceClass | None, str]] = {
    "°C": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    "%": (None, PERCENTAGE),
    "h": (SensorDeviceClass.DURATION, UnitOfTime.HOURS),
    "d": (SensorDeviceClass.DURATION, UnitOfTime.DAYS),
}


def describe_key(key: str) -> tuple[KeySpec | None, dict[str, str]]:
    """Return the presentation of a stable key and its name placeholders."""
    for pattern, translation_key, opts in _COMPILED:
        if match := pattern.match(key):
            placeholders = {"index": match.group(1)} if match.groups() else {}
            return KeySpec(translation_key=translation_key, **opts), placeholders
    return None, {}


def data_values(coordinator: BiostarCoordinator) -> dict[str, tuple[Any, str | None]]:
    """Return the values exposed as sensors (controls excluded)."""
    data = coordinator.data
    values = dict(data.values)
    if coordinator.client.has_write_access:
        # With a write key the programs are select entities instead.
        for key in list(values):
            if key == "program" or key.startswith("heating_circulation_program_"):
                del values[key]
    else:
        # With a write key these are number entities instead.
        for nr, circuit in data.circuits.items():
            if circuit.day_temp is not None:
                values[f"heating_circuit_{nr}_day_target"] = (circuit.day_temp, "°C")
            if circuit.night_temp is not None:
                values[f"heating_circuit_{nr}_night_target"] = (
                    circuit.night_temp,
                    "°C",
                )
    return values


def extra_unique_suffix(label: str, stable_keys: set[str]) -> str:
    """Unique ID suffix for a label the guntamatic library does not know.

    Same format as 1.x so these entities survive the upgrade.
    """
    suffix = slugify(label)
    if suffix in stable_keys or suffix in LIBRARY_KEYS or describe_key(suffix)[0]:
        return f"raw_{suffix}"
    return suffix


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BiostarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for every value the boiler reports, as they appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()
    known_extras: set[str] = set()

    @callback
    def _async_add_new() -> None:
        entities: list[SensorEntity] = []
        values = data_values(coordinator)
        for key, (value, unit) in values.items():
            if key in known:
                continue
            known.add(key)
            entities.append(BiostarSensor(coordinator, key, unit))
        for label, (value, unit) in coordinator.data.extras.items():
            if label in known_extras or isinstance(value, bool):
                continue
            known_extras.add(label)
            entities.append(
                BiostarExtraSensor(
                    coordinator, label, unit, extra_unique_suffix(label, set(values))
                )
            )
        if entities:
            async_add_entities(entities)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


def _apply_unit(entity: SensorEntity, unit: str | None) -> None:
    if unit in UNIT_METADATA:
        device_class, native_unit = UNIT_METADATA[unit]
        entity._attr_device_class = device_class
        entity._attr_native_unit_of_measurement = native_unit
        entity._attr_state_class = SensorStateClass.MEASUREMENT
    elif unit in NUMERIC_UNITS:
        # Values with these units are converted to numbers by the API client.
        entity._attr_native_unit_of_measurement = unit
        entity._attr_state_class = SensorStateClass.MEASUREMENT


class BiostarSensor(BiostarEntity, SensorEntity):
    """Sensor for one stable data key."""

    def __init__(
        self, coordinator: BiostarCoordinator, key: str, unit: str | None
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, slugify(key))
        self._key = key
        _apply_unit(self, unit)

        spec, placeholders = describe_key(key)
        if spec is None:
            # A key added by a newer guntamatic library: still show it.
            self._attr_name = key.replace("_", " ").capitalize()
            return
        self._attr_translation_key = spec.translation_key
        self._attr_translation_placeholders = placeholders
        if spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = spec.enabled_default
        if spec.state_class is not None and self._attr_native_unit_of_measurement:
            self._attr_state_class = spec.state_class

    @property
    def native_value(self) -> StateType:
        """Return the current value."""
        entry = data_values(self.coordinator).get(self._key)
        return None if entry is None else entry[0]

    @property
    def available(self) -> bool:
        """Unavailable when the boiler stops reporting this value."""
        return super().available and self._key in data_values(self.coordinator)


class BiostarExtraSensor(BiostarEntity, SensorEntity):
    """Value with a label the guntamatic library cannot translate (yet).

    The name follows the boiler language, so it is disabled by default.
    """

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: BiostarCoordinator,
        label: str,
        unit: str | None,
        unique_suffix: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, unique_suffix)
        self._label = label
        self._attr_name = label
        _apply_unit(self, unit)

    @property
    def native_value(self) -> StateType:
        """Return the current value."""
        entry = self.coordinator.data.extras.get(self._label)
        return None if entry is None else entry[0]

    @property
    def available(self) -> bool:
        """Unavailable when the boiler stops reporting this value."""
        return super().available and self._label in self.coordinator.data.extras
