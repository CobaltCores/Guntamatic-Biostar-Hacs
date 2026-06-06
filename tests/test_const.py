"""Tests for Guntamatic Biostar constants/helpers."""

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfTime

from custom_components.guntamatic_biostar.const import (
    get_sensor_metadata,
    is_program_state_key,
    normalize_program_option,
)


def test_time_metadata_distinguishes_runtime_from_countdown():
    """Test time sensors do not all become total increasing counters."""
    runtime = get_sensor_metadata("Betrieb Stunden", "h")
    countdown = get_sensor_metadata("_Nettoyage dans", "h")

    assert runtime["unit"] == UnitOfTime.HOURS
    assert runtime["state_class"] == SensorStateClass.TOTAL_INCREASING
    assert countdown["state_class"] == SensorStateClass.MEASUREMENT


def test_program_state_normalization():
    """Test raw program values from multiple languages."""
    assert normalize_program_option(0) == "off"
    assert normalize_program_option("Chauffage") == "heat"
    assert normalize_program_option("Absenken") == "lower"
    assert normalize_program_option("Normal") == "normal"
    assert normalize_program_option("unknown") is None


def test_program_state_key_detection_is_explicit():
    """Test program detection avoids unrelated keys."""
    assert is_program_state_key("_Mode")
    assert is_program_state_key("program")
    assert not is_program_state_key("_Circuit 1 - Mode")
