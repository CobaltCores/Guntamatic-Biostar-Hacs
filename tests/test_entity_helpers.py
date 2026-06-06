"""Tests for Guntamatic Biostar entity helpers."""

from types import SimpleNamespace

from custom_components.guntamatic_biostar.entity_helpers import (
    config_entry_unique_id,
    device_info_for_entry,
    dynamic_entity_unique_id,
    migrated_dynamic_entity_unique_id,
)


def _entry(**kwargs):
    defaults = {
        "unique_id": "boiler-serial-123",
        "data": {"host": "192.168.1.165"},
        "entry_id": "entry-id",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_config_entry_unique_id_prefers_config_entry_unique_id():
    """Test stable config entry identifier selection."""
    assert config_entry_unique_id(_entry()) == "boiler-serial-123"


def test_config_entry_unique_id_falls_back_to_host_then_entry_id():
    """Test fallback identifiers."""
    assert config_entry_unique_id(_entry(unique_id=None)) == "192.168.1.165"
    assert config_entry_unique_id(_entry(unique_id=None, data={})) == "entry-id"


def test_dynamic_entity_unique_id_includes_config_entry_identifier():
    """Test dynamic entity unique IDs are scoped by config entry."""
    assert (
        dynamic_entity_unique_id(_entry(), "_Température chaudière")
        == "boiler-serial-123_temperature_chaudiere"
    )


def test_migrated_dynamic_entity_unique_id_keeps_existing_suffix():
    """Test v1 dynamic unique ID migration."""
    assert (
        migrated_dynamic_entity_unique_id(
            _entry(unique_id="guntamatic_biostar_192.168.1.165"),
            "biostar_temperature_chaudiere",
        )
        == "guntamatic_biostar_192.168.1.165_temperature_chaudiere"
    )
    assert migrated_dynamic_entity_unique_id(_entry(), "other_temp") is None


def test_device_info_uses_one_identifier_for_all_platforms():
    """Test device info is shared across entity platforms."""
    info = device_info_for_entry(
        _entry(),
        {"typ": "Biostar 15", "sw_version": "4.0", "sn": "SN123"},
    )

    assert info["identifiers"] == {("guntamatic_biostar", "boiler-serial-123")}
    assert info["name"] == "Guntamatic Biostar 15"
    assert info["serial_number"] == "SN123"
