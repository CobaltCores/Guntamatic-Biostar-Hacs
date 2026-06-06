"""Entity helper functions for the Guntamatic Biostar integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from .const import (
    DATA_SCHEMA_HOST,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    OLD_DYNAMIC_ENTITY_UNIQUE_ID_PREFIX,
)


def config_entry_unique_id(config_entry: ConfigEntry) -> str:
    """Return the stable identifier used for this config entry."""
    if config_entry.unique_id:
        return config_entry.unique_id

    host = config_entry.data.get(DATA_SCHEMA_HOST)
    if host:
        return str(host)

    return config_entry.entry_id


def dynamic_entity_unique_id(config_entry: ConfigEntry, sensor_key: str) -> str:
    """Return a stable unique ID for a dynamic sensor/binary sensor."""
    return f"{config_entry_unique_id(config_entry)}_{slugify(sensor_key)}"


def migrated_dynamic_entity_unique_id(
    config_entry: ConfigEntry, old_unique_id: str
) -> str | None:
    """Return the v2 unique ID for a v1 dynamic entity unique ID."""
    if not old_unique_id.startswith(OLD_DYNAMIC_ENTITY_UNIQUE_ID_PREFIX):
        return None

    suffix = old_unique_id.removeprefix(OLD_DYNAMIC_ENTITY_UNIQUE_ID_PREFIX)
    if not suffix:
        return None

    return f"{config_entry_unique_id(config_entry)}_{suffix}"


def device_info_for_entry(
    config_entry: ConfigEntry, api_device_info: dict[str, Any] | None
) -> DeviceInfo:
    """Return shared device info for all entities of one boiler."""
    model = MODEL
    sw_version = None
    serial = None

    if api_device_info:
        model = api_device_info.get("typ") or MODEL
        sw_version = api_device_info.get("sw_version")
        serial = api_device_info.get("sn")

    return DeviceInfo(
        identifiers={(DOMAIN, config_entry_unique_id(config_entry))},
        name=f"Guntamatic {model}",
        manufacturer=MANUFACTURER,
        model=model,
        sw_version=sw_version,
        serial_number=serial,
    )
