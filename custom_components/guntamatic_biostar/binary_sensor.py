"""Binary sensors for the Guntamatic Biostar integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BiostarConfigEntry, BiostarCoordinator
from .entity import BiostarEntity
from .sensor import extra_unique_suffix

PARALLEL_UPDATES = 0

NO_FAULT_TEXTS = {"", "0", "-", "--", "---"}


def active_faults(coordinator: BiostarCoordinator) -> list[str]:
    """Return the fault messages currently reported by the boiler.

    status.cgi has a structured error list. Without it, fall back to the
    free text fault lines of the legacy endpoints, whose "no fault" value is
    not documented (empty on the boilers seen so far).
    """
    data = coordinator.data
    if data.has_status:
        return list(data.errors)
    messages: list[str] = []
    for key, (value, _unit) in sorted(data.values.items()):
        if not key.startswith("interruption_") or value is None:
            continue
        text = str(value).strip()
        if text not in NO_FAULT_TEXTS and text not in messages:
            messages.append(text)
    return messages


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BiostarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the fault sensor and on/off values with unknown labels."""
    coordinator = entry.runtime_data
    async_add_entities([BiostarFaultSensor(coordinator)])
    known: set[str] = set()

    @callback
    def _async_add_new() -> None:
        entities = []
        for label, (value, _unit) in coordinator.data.extras.items():
            if label in known or not isinstance(value, bool):
                continue
            known.add(label)
            entities.append(
                BiostarExtraBinarySensor(
                    coordinator,
                    label,
                    extra_unique_suffix(label, set(coordinator.data.values)),
                )
            )
        if entities:
            async_add_entities(entities)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class BiostarFaultSensor(BiostarEntity, BinarySensorEntity):
    """On while the boiler reports a fault."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "fault"

    def __init__(self, coordinator: BiostarCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "fault")

    @property
    def is_on(self) -> bool:
        """Return true while a fault is active."""
        return bool(active_faults(self.coordinator))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the fault messages."""
        return {"messages": active_faults(self.coordinator)}


class BiostarExtraBinarySensor(BiostarEntity, BinarySensorEntity):
    """On/off value with a label the guntamatic library does not know."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: BiostarCoordinator, label: str, unique_suffix: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, unique_suffix)
        self._label = label
        self._attr_name = label

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        entry = self.coordinator.data.extras.get(self._label)
        return None if entry is None else entry[0]

    @property
    def available(self) -> bool:
        """Unavailable when the boiler stops reporting this value."""
        return super().available and self._label in self.coordinator.data.extras
