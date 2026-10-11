"""Tests for the Guntamatic Biostar API client."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.guntamatic_biostar.api import (
    PROGRAMS,
    BiostarClient,
    BiostarCommandError,
    BiostarConnectionError,
    normalize_program,
    parse_legacy,
)

from .const import API_KEY, BASE, DAQDATA, DAQDESC, HOST, STATUS, WRITE_KEY, mock_boiler


def _client(hass: HomeAssistant, **kwargs) -> BiostarClient:
    return BiostarClient(
        session=async_get_clientsession(hass),
        host=HOST,
        api_key=API_KEY,
        **kwargs,
    )


def test_parse_legacy_uses_stable_keys_and_filters_placeholders():
    """French labels become stable keys, unconnected slots disappear."""
    values, extras = parse_legacy(
        DAQDESC.decode("windows-1252").splitlines(),
        DAQDATA.decode("windows-1252").splitlines(),
    )

    assert values["boiler_temperature"] == (65.0, "°C")
    assert values["outdoor_temperature"] == (7.1, "°C")
    assert values["buffer_load"] == (42.0, "%")
    assert values["program"] == ("heat", None)
    assert values["heating_circulation_program_1"] == ("timer", None)
    assert values["heating_circulation_pump_1"] == ("nonstop", None)
    assert values["serial"] == ("959103", None)
    assert values["operating_time"] == (1122.0, "h")
    # Service time is exposed in both units.
    assert values["service_days"] == (78.0, "d")
    assert values["service_hours"] == (1872.0, "h")
    # Placeholder slots are gone, with everything that belongs to them.
    for key in (
        "domestic_hot_water_1_temperature",
        "dhw_pump_1",
        "room_0_temperature",
        "circuit_0_temp",
        "heating_circulation_pump_0",
        "heating_circulation_program_0",
    ):
        assert key not in values
    # Empty fault line has no value.
    assert values["interruption_1"] == (None, None)
    # Reserved lines are skipped, unknown labels are kept apart.
    assert not any("serv" in label for label in extras)
    assert extras == {"Truc inconnu": (12.5, "°C"), "Relais X": (True, None)}


def test_normalize_program():
    """Programs are normalized from indexes, canonical names and labels."""
    table = {"chauffage": "heat", "normal": "timer"}
    assert normalize_program(3, table, PROGRAMS) == "heat"
    assert normalize_program("6", table, PROGRAMS) == "dhw_boost"
    assert normalize_program("CHAUFFAGE", table, PROGRAMS) == "heat"
    assert normalize_program("dhw", table, PROGRAMS) == "dhw"
    assert normalize_program("Inconnu", table, PROGRAMS) == "Inconnu"
    assert normalize_program(None, table, PROGRAMS) is None


async def test_get_data_merges_without_duplicates(hass: HomeAssistant, boiler):
    """status.cgi and legacy values share keys; legacy wins, status fills gaps."""
    data = await _client(hass).async_get_data()

    # Legacy value wins over the status.cgi copy of the same measurement.
    assert data.values["boiler_temperature"] == (65.0, "°C")
    # status.cgi only values.
    assert data.values["flue_gas"] == (59.0, "%")
    assert data.values["fuel_level"] == (80.0, "%")
    assert data.values["ash_empty_in"] == (49.0, "h")
    assert data.values["version"] == ("32a", None)
    assert data.meta["typ"] == "Biostar 15"
    circuit = data.circuits[1]
    assert (circuit.name, circuit.day_temp, circuit.night_temp) == (
        "Maison",
        21.0,
        17.0,
    )
    assert circuit.program == "timer"
    # No key spelled in the boiler language.
    assert all(key.isascii() and key == key.lower() for key in data.values)


async def test_get_data_status_only(hass: HomeAssistant, aioclient_mock):
    """Without legacy endpoints the status.cgi values use the same keys."""
    mock_boiler(aioclient_mock)
    data = await _client(hass, include_legacy=False).async_get_data()

    assert data.values["boiler_temperature"] == (64.5, "°C")
    assert data.values["program"] == ("heat", None)
    assert data.values["serial"] == ("959103", None)
    assert data.values["domestic_hot_water_0_temperature"] == (45.0, "°C")
    assert data.extras == {}
    assert not any("daq" in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_get_data_keeps_status_serial_when_legacy_is_empty(
    hass: HomeAssistant, aioclient_mock
):
    """An empty legacy line does not erase a status.cgi value."""
    aioclient_mock.get(f"{BASE}/status.cgi", json=STATUS)
    aioclient_mock.get(f"{BASE}/daqdesc.cgi", content="Série; \n".encode("cp1252"))
    aioclient_mock.get(f"{BASE}/daqdata.cgi", content=b"\n")
    data = await _client(hass).async_get_data()
    assert data.values["serial"] == ("959103", None)


async def test_get_data_legacy_failure(hass: HomeAssistant, aioclient_mock):
    """Legacy failure is tolerated with status.cgi, fatal without it."""
    mock_boiler(aioclient_mock, legacy=False)
    data = await _client(hass).async_get_data()
    assert data.values["boiler_temperature"] == (64.5, "°C")

    aioclient_mock.clear_requests()
    mock_boiler(aioclient_mock, status=None, legacy=False)
    with pytest.raises(BiostarConnectionError):
        await _client(hass).async_get_data()


def _sent(aioclient_mock) -> list[dict[str, str]]:
    calls = []
    for method, url, _data, _headers in aioclient_mock.mock_calls:
        if "parset" in url.path:
            calls.append({k: v[0] for k, v in parse_qs(url.query_string).items()})
    return calls


@pytest.mark.parametrize(
    ("program", "value"),
    [
        ("off", "0"),
        ("timer", "1"),
        ("dhw", "2"),
        ("heat", "3"),
        ("hibernate", "4"),
        ("dhw_boost", "6"),
    ],
)
async def test_set_program_uses_boiler_enum_index(
    hass: HomeAssistant, aioclient_mock, program, value
):
    """PR001 values follow the order of the boiler parameter table."""
    aioclient_mock.get(f"{BASE}/ext/parset.cgi", json={"ack": "ok"})
    await _client(hass, write_key=WRITE_KEY).async_set_program(program)
    assert _sent(aioclient_mock) == [{"syn": "PR001", "value": value, "key": WRITE_KEY}]


async def test_circuit_commands_use_circuit_number(hass: HomeAssistant, aioclient_mock):
    """HKx01/HKx04/HKx05 use the circuit number as shown by the boiler."""
    aioclient_mock.get(f"{BASE}/ext/parset.cgi", json={"ack": "ok"})
    client = _client(hass, write_key=WRITE_KEY)
    await client.async_set_circuit_program(1, "hibernate")
    await client.async_set_circuit_temperature(1, "day", 21.5)
    await client.async_set_circuit_temperature(0, "night", 17)
    assert _sent(aioclient_mock) == [
        {"syn": "HK101", "value": "3", "key": WRITE_KEY},
        {"syn": "HK104", "value": "21.50", "key": WRITE_KEY},
        {"syn": "HK005", "value": "17.00", "key": WRITE_KEY},
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"json": {"err": "invalid value"}}, "refused"),
        ({"json": {"something": "else"}}, "did not confirm"),
        ({"text": "OK"}, "unexpected answer"),
        ({"status": 500}, "HTTP 500"),
    ],
)
async def test_write_requires_acknowledgement(
    hass: HomeAssistant, aioclient_mock, kwargs, message
):
    """A write only succeeds when the boiler answers with ack."""
    aioclient_mock.get(f"{BASE}/ext/parset.cgi", **kwargs)
    with pytest.raises(BiostarCommandError, match=message):
        await _client(hass, write_key=WRITE_KEY).async_set_program("heat")


async def test_write_falls_back_to_parset_without_ext(
    hass: HomeAssistant, aioclient_mock
):
    """Firmware without /ext/ gets the command on /parset.cgi."""
    aioclient_mock.get(f"{BASE}/ext/parset.cgi", status=404)
    aioclient_mock.get(f"{BASE}/parset.cgi", json={"ack": "ok"})
    await _client(hass, write_key=WRITE_KEY).async_set_program("off")
    assert len(_sent(aioclient_mock)) == 2


async def test_write_validation(hass: HomeAssistant, aioclient_mock):
    """Invalid commands never reach the boiler."""
    with pytest.raises(BiostarCommandError):
        await _client(hass).async_set_program("heat")
    client = _client(hass, write_key=WRITE_KEY)
    with pytest.raises(BiostarCommandError):
        await client.async_set_program("lower")
    with pytest.raises(BiostarCommandError):
        await client.async_set_circuit_program(9, "heat")
    with pytest.raises(BiostarCommandError):
        await client.async_set_circuit_program(1, "dhw")
    assert aioclient_mock.call_count == 0


def test_library_warnings_are_not_repeated(caplog):
    """The library's per-poll "Untranslated string" warning is logged once."""
    descriptions = ["program.; ", "Série; "]
    values = ["INCONNU", "1"]
    parse_legacy(descriptions, values)
    parse_legacy(descriptions, values)
    assert caplog.text.count("Untranslated string detected for INCONNU") == 1


def test_parse_legacy_fault_lines_numbered_from_zero():
    """Firmware 3.x numbers fault lines from 0; the second one is not lost."""
    values, extras = parse_legacy(
        ["Série; ", "Defaut 0; ", "Defaut 1; "],
        ["1", "F23 Sonde fumées", "F41 Allumage"],
    )
    assert values["interruption_1"] == ("F23 Sonde fumées", None)
    assert values["interruption_2"] == ("F41 Allumage", None)
    assert extras == {}


def test_parse_legacy_fault_lines_numbered_from_one():
    """Older firmware numbers them from 1, as the library expects."""
    values, _extras = parse_legacy(
        ["Série; ", "Defaut 1; ", "Defaut 2; "],
        ["1", "F23 Sonde fumées", ""],
    )
    assert values["interruption_1"] == ("F23 Sonde fumées", None)
    assert values["interruption_2"] == (None, None)


async def test_real_biostar_fw33_capture(hass: HomeAssistant, aioclient_mock):
    """Capture of a Biostar 15 kW, firmware 3.3c, French UI (serials changed).

    One heating circuit (CH0, status.cgi nr "0"), no buffer tank, no hot
    water circuit.
    """
    fixtures = Path(__file__).parent / "fixtures"
    aioclient_mock.get(
        f"{BASE}/status.cgi",
        content=(fixtures / "fw33_fr_status.json").read_bytes(),
    )
    aioclient_mock.get(
        f"{BASE}/daqdesc.cgi", content=(fixtures / "fw33_fr_daqdesc.txt").read_bytes()
    )
    aioclient_mock.get(
        f"{BASE}/daqdata.cgi", content=(fixtures / "fw33_fr_daqdata.txt").read_bytes()
    )
    data = await _client(hass).async_get_data()

    assert set(data.circuits) == {0}
    assert data.circuits[0].numbered
    assert data.circuits[0].name == "Radiateurs"
    assert data.constraints["min"] == 15.0
    # status.cgi enum wins over the localized state of the legacy line.
    assert data.values["heating_circulation_program_0"] == ("timer", None)
    assert data.values["program"] == ("timer", None)
    assert data.values["room_0_temperature"] == (20.16, "°C")
    assert data.values["heating_circulation_pump_0"] == ("on", None)
    assert data.values["boiler_temperature"] == (42.64, "°C")
    # status.cgi fractions become percentages.
    assert data.values["flue_gas"] == (32.0, "%")
    assert data.values["fuel_level"] == (0.0, "%")
    # Missing probes (120 / -100 / -20 °C) and their companions are gone.
    for key in (
        "buffer_top_temperature",
        "buffer_center_temperature",
        "buffer_bottom_temperature",
        "buffer_t5_temperature",
        "buffer_t6_temperature",
        "buffer_t7_temperature",
        "buffer_load",
        "domestic_hot_water_0_temperature",
        "dhw_pump_0",
        "extra_dhw_0_temperature",
        "room_1_temperature",
        "circuit_1_temp",
    ):
        assert key not in data.values, key
    # "Defaut 0" and "Defaut 1" are two fault lines.
    assert data.values["interruption_1"] == (None, None)
    assert data.values["interruption_2"] == (None, None)
    assert data.extras == {}
    assert data.errors == []
