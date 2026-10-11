"""Base entity for the Guntamatic Biostar integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BiostarCoordinator
from .entity_helpers import device_info_for_entry


class BiostarEntity(CoordinatorEntity[BiostarCoordinator]):
    """Entity attached to the boiler device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BiostarCoordinator, unique_suffix: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_unique_id}_{unique_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the boiler device."""
        meta = self.coordinator.data.meta if self.coordinator.data else None
        return device_info_for_entry(self.coordinator.config_entry, meta)
