"""Tests for the Guntamatic Biostar integration setup, entities and migration."""

from __future__ import annotations

from urllib.parse import parse_qs

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.guntamatic_biostar.const import (
    CONF_INCLUDE_LEGACY,
    DOMAIN,
)

from .const import API_KEY, BASE, HOST, STATUS, WRITE_KEY, mock_boiler

SERIAL = "959103"


def _entry(
    write_key: str | None = None, version: int = 3, **options
) -> MockConfigEntry:
    data = {"host": HOST, "api_key": API_KEY}
    if write_key:
        data["write_key"] = write_key
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        data=data,
        options={CONF_INCLUDE_LEGACY: True, **options},
        version=version,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(hass: HomeAssistant, domain: str, suffix: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{SERIAL}_{suffix}")


async def test_setup_creates_stable_sensors(hass: HomeAssistant, boiler):
    """Sensors use stable keys, translated names and no duplicates."""
    entry = _entry()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    boiler_temp = _entity_id(hass, "sensor", "boiler_temperature")
    state = hass.states.get(boiler_temp)
    assert state.state == "65.0"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert (
        state.attributes["friendly_name"] == "Guntamatic Biostar 15 Boiler temperature"
    )

    room = hass.states.get(_entity_id(hass, "sensor", "room_1_temperature"))
    assert (
        room.attributes["friendly_name"]
        == "Guntamatic Biostar 15 Room temperature circuit 1"
    )
    assert hass.states.get(_entity_id(hass, "sensor", "program")).state == "heat"

    # Without a write key the circuit set points are read-only sensors.
    assert (
        hass.states.get(
            _entity_id(hass, "sensor", "heating_circuit_1_day_target")
        ).state
        == "21.0"
    )
    assert _entity_id(hass, "number", "1_day_temp") is None
    assert _entity_id(hass, "select", "program") is None

    # Placeholder slots never become entities.
    assert _entity_id(hass, "sensor", "room_0_temperature") is None
    assert _entity_id(hass, "sensor", "domestic_hot_water_1_temperature") is None

    # Exactly one boiler temperature entity.
    registry = er.async_get(hass)
    keys = [
        e.translation_key
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    ]
    assert keys.count("boiler_temperature") == 1

    # Unknown labels exist but are disabled by default.
    extra = registry.async_get(_entity_id(hass, "sensor", "truc_inconnu"))
    assert extra.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    relay = registry.async_get(_entity_id(hass, "binary_sensor", "relais_x"))
    assert relay.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    assert (
        hass.states.get(_entity_id(hass, "binary_sensor", "fault")).state == STATE_OFF
    )

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_fault_sensor(hass: HomeAssistant, aioclient_mock):
    """The fault sensor turns on with status.cgi errors."""
    mock_boiler(aioclient_mock, status={**STATUS, "error": ["F23 Sonde fumées"]})
    await _setup(hass, _entry())
    state = hass.states.get(_entity_id(hass, "binary_sensor", "fault"))
    assert state.state == STATE_ON
    assert state.attributes["messages"] == ["F23 Sonde fumées"]


def _parset_calls(aioclient_mock) -> list[dict[str, str]]:
    return [
        {k: v[0] for k, v in parse_qs(url.query_string).items()}
        for _m, url, _d, _h in aioclient_mock.mock_calls
        if "parset" in url.path
    ]


async def test_write_entities(hass: HomeAssistant, boiler, caplog):
    """With a write key, programs and set points are controls."""
    boiler.get(f"{BASE}/ext/parset.cgi", json={"ack": "ok"})
    await _setup(hass, _entry(write_key=WRITE_KEY))

    program = _entity_id(hass, "select", "program")
    assert hass.states.get(program).state == "heat"
    assert "dhw" in hass.states.get(program).attributes["options"]
    circuit = _entity_id(hass, "select", "circuit_1_program")
    assert hass.states.get(circuit).state == "timer"
    day = _entity_id(hass, "number", "1_day_temp")
    assert hass.states.get(day).state == "21.0"
    # The controls replace the read-only sensors.
    assert _entity_id(hass, "sensor", "program") is None
    assert _entity_id(hass, "sensor", "heating_circuit_1_day_target") is None

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": program, "option": "dhw"},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": circuit, "option": "hibernate"},
        blocking=True,
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": day, "value": 20.5}, blocking=True
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": day, "value": 21.1}, blocking=True
    )
    assert _parset_calls(boiler) == [
        {"syn": "PR001", "value": "2", "key": WRITE_KEY},
        {"syn": "HK101", "value": "3", "key": WRITE_KEY},
        {"syn": "HK104", "value": "20.50", "key": WRITE_KEY},
        # Rounded to the 0.5 step the boiler accepts.
        {"syn": "HK104", "value": "21.00", "key": WRITE_KEY},
    ]
    # The mocked boiler keeps reporting the old program: that gets flagged.
    assert "acknowledged program dhw but does not report it" in caplog.text
    # 21.0 is what the mocked boiler reports, so no warning for that one.
    assert "set point 21.0 °C" not in caplog.text


async def test_refused_write_raises(hass: HomeAssistant, boiler):
    """A refused command shows an error instead of failing silently."""
    boiler.get(f"{BASE}/ext/parset.cgi", json={"err": "not allowed"})
    await _setup(hass, _entry(write_key=WRITE_KEY))
    with pytest.raises(HomeAssistantError, match="not allowed"):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": _entity_id(hass, "select", "program"), "option": "off"},
            blocking=True,
        )


async def test_migration_from_language_labels(hass: HomeAssistant, boiler):
    """1.x entities keep their entity IDs, duplicates are left alone."""
    entry = _entry(version=2)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    def add(domain: str, suffix: str, object_id: str) -> str:
        return registry.async_get_or_create(
            domain,
            DOMAIN,
            f"{SERIAL}_{suffix}",
            config_entry=entry,
            suggested_object_id=object_id,
        ).entity_id

    legacy_temp = add("sensor", "temp_chaudiere", "biostar_temp_chaudiere")
    status_temp = add(
        "sensor", "temperature_chaudiere", "biostar_temperature_chaudiere"
    )
    fumes = add("sensor", "fumees", "biostar_fumees")
    room = add("sensor", "temp_amb_ch_1", "biostar_temp_amb_ch_1")
    unknown = add("sensor", "truc_inconnu", "biostar_truc_inconnu")
    number = add("number", "1_day_temp", "biostar_jour")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 3

    assert registry.async_get(legacy_temp).unique_id == f"{SERIAL}_boiler_temperature"
    # The duplicate keeps its old unique ID instead of being deleted.
    assert (
        registry.async_get(status_temp).unique_id == f"{SERIAL}_temperature_chaudiere"
    )
    assert registry.async_get(fumes).unique_id == f"{SERIAL}_flue_gas"
    assert registry.async_get(room).unique_id == f"{SERIAL}_room_1_temperature"
    assert registry.async_get(unknown).unique_id == f"{SERIAL}_truc_inconnu"
    assert registry.async_get(number).unique_id == f"{SERIAL}_1_day_temp"
    # Same entity, now fed by the stable key.
    assert hass.states.get(legacy_temp).state == "65.0"
    assert hass.states.get(room).state == "21.5"


async def test_migration_prefers_enabled_duplicate(hass: HomeAssistant, boiler):
    """When the legacy copy was disabled, the status.cgi entity takes the key."""
    entry = _entry(version=2)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    legacy = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{SERIAL}_temp_chaudiere",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    ).entity_id
    status = registry.async_get_or_create(
        "sensor", DOMAIN, f"{SERIAL}_temperature_chaudiere", config_entry=entry
    ).entity_id

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(status).unique_id == f"{SERIAL}_boiler_temperature"
    assert registry.async_get(legacy).unique_id == f"{SERIAL}_temp_chaudiere"
    assert hass.states.get(status).state == "65.0"


async def test_circuit_without_number_gets_no_controls(
    hass: HomeAssistant, aioclient_mock
):
    """Never write to a circuit whose number is only a list position."""
    circuit = {"name": "Maison", "day_temp": 21.0, "night_temp": 17.0, "mode": "NORMAL"}
    mock_boiler(aioclient_mock, status={**STATUS, "heat_circ": [circuit]}, legacy=False)
    await _setup(hass, _entry(write_key=WRITE_KEY))
    assert _entity_id(hass, "number", "0_day_temp") is None
    assert _entity_id(hass, "select", "circuit_0_program") is None
    assert _entity_id(hass, "select", "program") is not None


async def test_legacy_only_fault_and_on_off_pumps(hass: HomeAssistant, aioclient_mock):
    """Without status.cgi, fault lines drive the fault sensor; ON/OFF pumps are on/off."""
    lines = [
        ("Série; ", "959103"),
        ("Heating circulation pump 1; ", "ON"),
        ("Boil.shunt pump; ", "OFF"),
        ("Interuption 1; ", "F23 flue gas sensor"),
        ("Interuption 2; ", ""),
    ]
    aioclient_mock.get(f"{BASE}/status.cgi", status=404)
    aioclient_mock.get(
        f"{BASE}/daqdesc.cgi", content="\n".join(d for d, _ in lines).encode()
    )
    aioclient_mock.get(
        f"{BASE}/daqdata.cgi", content="\n".join(v for _, v in lines).encode()
    )
    await _setup(hass, _entry())

    fault = hass.states.get(_entity_id(hass, "binary_sensor", "fault"))
    assert fault.state == STATE_ON
    assert fault.attributes["messages"] == ["F23 flue gas sensor"]
    assert (
        hass.states.get(_entity_id(hass, "sensor", "heating_circulation_pump_1")).state
        == "on"
    )
    assert (
        hass.states.get(_entity_id(hass, "sensor", "boiler_shunt_pump")).state == "off"
    )
