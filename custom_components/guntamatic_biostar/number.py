"""Room set points for the Guntamatic Biostar integration (write key needed)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DEFAULT_CONSTRAINTS
from .coordinator import BiostarConfigEntry, BiostarCoordinator
from .entity import BiostarEntity

PARALLEL_UPDATES = 1
PERIODS = ("day", "night")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BiostarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up day/night set points for every heating circuit in status.cgi."""
    coordinator = entry.runtime_data
    if not coordinator.client.has_write_access:
        return
    known: set[int] = set()

    @callback
    def _async_add_new() -> None:
        circuits = coordinator.data.circuits
        new = {nr for nr, circuit in circuits.items() if circuit.numbered} - known
        known.update(new)
        if new:
            async_add_entities(
                BiostarSetPoint(coordinator, nr, period)
                for nr in sorted(new)
                for period in PERIODS
            )

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class BiostarSetPoint(BiostarEntity, NumberEntity):
    """Day or night room set point of a heating circuit (HKx04 / HKx05)."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: BiostarCoordinator, nr: int, period: str) -> None:
        """Initialize the number."""
        # Same unique ID as 1.x.
        super().__init__(coordinator, f"{nr}_{period}_temp")
        self._nr = nr
        self._period = period
        self._attr_translation_key = f"{period}_temperature"
        self._attr_translation_placeholders = {"index": str(nr)}

    def _constraint(self, name: str) -> float:
        return self.coordinator.data.constraints.get(name, DEFAULT_CONSTRAINTS[name])

    @property
    def native_min_value(self) -> float:
        """Return the lowest accepted set point."""
        return self._constraint("min")

    @property
    def native_max_value(self) -> float:
        """Return the highest accepted set point."""
        return self._constraint("max")

    @property
    def native_step(self) -> float:
        """Return the set point increment."""
        return self._constraint("inc")

    @property
    def native_value(self) -> float | None:
        """Return the current set point."""
        circuit = self.coordinator.data.circuits.get(self._nr)
        if circuit is None:
            return None
        return circuit.day_temp if self._period == "day" else circuit.night_temp

    @property
    def available(self) -> bool:
        """Unavailable when the circuit disappears from status.cgi."""
        return super().available and self._nr in self.coordinator.data.circuits

    async def async_set_native_value(self, value: float) -> None:
        """Write the set point, rounded to the step the boiler accepts."""
        step = self.native_step
        if step > 0:
            value = round(round(value / step) * step, 2)
        nr, period = self._nr, self._period

        def applied(data) -> bool:
            circuit = data.circuits.get(nr)
            if circuit is None:
                return False
            current = circuit.day_temp if period == "day" else circuit.night_temp
            return current is not None and abs(current - value) < 0.01

        await self.coordinator.async_command(
            self.coordinator.client.async_set_circuit_temperature(nr, period, value),
            f"{period} set point {value} °C on heating circuit {nr}",
            applied,
        )
