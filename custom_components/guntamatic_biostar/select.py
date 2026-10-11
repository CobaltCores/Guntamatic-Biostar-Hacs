"""Program selection for the Guntamatic Biostar integration (write key needed)."""

from __future__ import annotations

import re

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CIRCUIT_PROGRAMS, PROGRAMS
from .coordinator import BiostarConfigEntry, BiostarCoordinator
from .entity import BiostarEntity

PARALLEL_UPDATES = 1

_CIRCUIT_PROGRAM_KEY = re.compile(r"^heating_circulation_program_(\d+)$")


def configured_circuits(coordinator: BiostarCoordinator) -> set[int]:
    """Return the heating circuits whose number the boiler states explicitly."""
    circuits = {
        nr for nr, circuit in coordinator.data.circuits.items() if circuit.numbered
    }
    for key in coordinator.data.values:
        if match := _CIRCUIT_PROGRAM_KEY.match(key):
            circuits.add(int(match.group(1)))
    return circuits


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BiostarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up program selects when a write key is configured."""
    coordinator = entry.runtime_data
    if not coordinator.client.has_write_access:
        return

    async_add_entities([BiostarProgramSelect(coordinator)])
    known: set[int] = set()

    @callback
    def _async_add_new() -> None:
        new = configured_circuits(coordinator) - known
        known.update(new)
        if new:
            async_add_entities(
                BiostarCircuitProgramSelect(coordinator, nr) for nr in sorted(new)
            )

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class BiostarProgramSelect(BiostarEntity, SelectEntity):
    """Boiler program (PR001)."""

    _attr_translation_key = "heating_program"

    def __init__(self, coordinator: BiostarCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator, "program")
        self._attr_options = list(PROGRAMS)

    @property
    def current_option(self) -> str | None:
        """Return the active program."""
        value = self.coordinator.data.values.get("program", (None, None))[0]
        return value if value in PROGRAMS else None

    async def async_select_option(self, option: str) -> None:
        """Change the program."""
        await self.coordinator.async_command(
            self.coordinator.client.async_set_program(option),
            f"program {option}",
            lambda data: data.values.get("program", (None, None))[0] == option,
        )


class BiostarCircuitProgramSelect(BiostarEntity, SelectEntity):
    """Program of one heating circuit (HKx01)."""

    _attr_translation_key = "circuit_program"

    def __init__(self, coordinator: BiostarCoordinator, nr: int) -> None:
        """Initialize the select."""
        super().__init__(coordinator, f"circuit_{nr}_program")
        self._attr_options = list(CIRCUIT_PROGRAMS)
        self._nr = nr
        self._attr_translation_placeholders = {"index": str(nr)}

    @property
    def current_option(self) -> str | None:
        """Return the active circuit program."""
        key = f"heating_circulation_program_{self._nr}"
        value = self.coordinator.data.values.get(key, (None, None))[0]
        return value if value in CIRCUIT_PROGRAMS else None

    async def async_select_option(self, option: str) -> None:
        """Change the circuit program."""
        key = f"heating_circulation_program_{self._nr}"
        await self.coordinator.async_command(
            self.coordinator.client.async_set_circuit_program(self._nr, option),
            f"program {option} on heating circuit {self._nr}",
            lambda data: data.values.get(key, (None, None))[0] == option,
        )
