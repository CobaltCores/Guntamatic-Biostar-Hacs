"""Config entry migrations for the Guntamatic Biostar integration."""

from __future__ import annotations

import logging

from guntamatic.heater import TRANSLATE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import LEGACY_STATUS_LABELS
from .entity_helpers import config_entry_unique_id, migrated_dynamic_entity_unique_id

_LOGGER = logging.getLogger(__name__)


def stable_key_for_v2_suffix() -> tuple[dict[str, str], dict[str, str]]:
    """Return (legacy label slug -> key, status label slug -> key)."""
    legacy = {slugify(label): key for label, key in TRANSLATE.items()}
    status = {slugify(label): key for label, key in LEGACY_STATUS_LABELS.items()}
    return legacy, status


def _zero_based_fault_key(
    suffix: str, suffixes: set[str], legacy_map: dict[str, str]
) -> str | None:
    """Return the fault key of a "<fault label>_N" sensor numbered from 0.

    Firmware 3.x numbers fault lines from 0 ("Defaut 0", "Defaut 1") and the
    library maps both of them to interruption_1. A "_0" sibling tells such a
    boiler apart from older firmware numbering them from 1.
    """
    base, _, nr = suffix.rpartition("_")
    zero = f"{base}_0"
    if not nr.isdigit() or zero not in suffixes:
        return None
    if legacy_map.get(zero) != "interruption_1":
        return None
    return f"interruption_{int(nr) + 1}"


def migrate_v1_to_v2(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Scope v1 "biostar_<label>" unique IDs to the config entry."""
    entity_registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if registry_entry.domain not in {"sensor", "binary_sensor"}:
            continue
        new_unique_id = migrated_dynamic_entity_unique_id(
            entry, registry_entry.unique_id
        )
        if not new_unique_id or new_unique_id == registry_entry.unique_id:
            continue
        try:
            entity_registry.async_update_entity(
                registry_entry.entity_id, new_unique_id=new_unique_id
            )
        except ValueError as err:
            _LOGGER.warning(
                "Could not migrate unique ID for %s: %s", registry_entry.entity_id, err
            )


def migrate_v2_to_v3(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move sensors from language dependent labels to stable keys.

    Entity IDs (and therefore history, dashboards and automations) are kept.
    When the boiler value was exposed twice (once from status.cgi, once from
    the legacy endpoints) one entity gets the stable key: an enabled one over a
    disabled one, then the legacy one. The other is left untouched; it stops
    updating and the user can delete it.
    """
    entity_registry = er.async_get(hass)
    prefix = f"{config_entry_unique_id(entry)}_"
    legacy_map, status_map = stable_key_for_v2_suffix()

    registry_entries = [
        registry_entry
        for registry_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        if registry_entry.domain == "sensor"
        and registry_entry.unique_id.startswith(prefix)
    ]
    suffixes = {
        registry_entry.unique_id.removeprefix(prefix)
        for registry_entry in registry_entries
    }

    candidates: list[tuple[int, er.RegistryEntry, str]] = []
    for registry_entry in registry_entries:
        suffix = registry_entry.unique_id.removeprefix(prefix)
        if fault_key := _zero_based_fault_key(suffix, suffixes, legacy_map):
            candidates.append((0, registry_entry, fault_key))
        elif suffix in legacy_map:
            candidates.append((0, registry_entry, legacy_map[suffix]))
        elif suffix in status_map:
            candidates.append((1, registry_entry, status_map[suffix]))

    # Enabled before disabled, then legacy before status.cgi.
    candidates.sort(
        key=lambda item: (
            item[1].disabled_by is not None,
            item[0],
            item[1].entity_id,
        )
    )
    for _, registry_entry, key in candidates:
        new_unique_id = f"{prefix}{key}"
        if new_unique_id == registry_entry.unique_id:
            continue
        existing = entity_registry.async_get_entity_id(
            "sensor", registry_entry.platform, new_unique_id
        )
        if existing:
            _LOGGER.warning(
                "%s duplicates %s (both show %s); it will stop updating, "
                "delete it once your dashboards and automations use %s",
                registry_entry.entity_id,
                existing,
                key,
                existing,
            )
            continue
        entity_registry.async_update_entity(
            registry_entry.entity_id, new_unique_id=new_unique_id
        )
