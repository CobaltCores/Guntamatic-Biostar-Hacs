"""Local API client for Guntamatic Biostar boilers.

This module has no Home Assistant dependency so it can be tested on its own.

Reading uses two sources:

* ``/status.cgi`` (JSON, needs the API key): device meta data, heating
  circuits with their set points, errors and a few values the legacy
  endpoints do not expose.
* ``/daqdesc.cgi`` + ``/daqdata.cgi`` (legacy, one line per value): the bulk
  of the sensors. Their labels follow the language configured on the boiler,
  so they are normalised to stable English keys with the ``guntamatic``
  library (the one behind the official Home Assistant integration). That
  library also drops placeholder values reported by unconnected slots and
  translates enum values (programs, pump modes) to canonical English.

Writing uses ``/ext/parset.cgi`` with the write key. Parameter IDs and enum
indexes come from the boiler's own parameter table (``par.cgi`` export of a
Biostar on firmware 3.2a)::

    PR001  program          OFF;NORMAL;DHW;HEAT;HIBERNATE;HIBERNATE TO;DHW BOOST
    HKx01  circuit program  OFF;NORMAL;HEAT;HIBERNATE;HIBERNATE TO
    HKx04  circuit day set point   (5.00 - 30.00, step 0.50)
    HKx05  circuit night set point (5.00 - 30.00, step 0.50)

where ``x`` is the circuit number as shown by the boiler (0-8).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from guntamatic.heater import (
    RESERVED,
    SERIAL,
    TRANSLATE,
    TRANSLATE_HC_PROGRAM,
    TRANSLATE_PROGRAM,
    Heater,
    NoSerialException,
)

_LOGGER = logging.getLogger(__name__)

ENCODING = "windows-1252"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Enum order of PR001 on the boiler; the index is the value to write.
PROGRAMS: tuple[str, ...] = (
    "off",
    "timer",
    "dhw",
    "heat",
    "hibernate",
    "hibernate_to",
    "dhw_boost",
)
# Enum order of HKx01 (heating circuit program).
CIRCUIT_PROGRAMS: tuple[str, ...] = (
    "off",
    "timer",
    "heat",
    "hibernate",
    "hibernate_to",
)
CIRCUIT_COUNT = 9
DEFAULT_CONSTRAINTS = {"min": 5.0, "max": 30.0, "inc": 0.5}

NUMERIC_UNITS = {"°C", "%", "h", "d", "kW", "m3", "m³", "kg"}
EXTRA_RESERVED = ("reserviert",)
TRUE_VALUES = {"AN", "ON", "MARCHE", "EIN"}
FALSE_VALUES = {"AUS", "OFF", "ARRÊT", "ARRET"}
PLACEHOLDER_TEMPERATURES = {-20.0, -9.0}
# Readings of a missing sensor on firmware 3.3 (open circuit / not
# configured): buffer and hot water probes report 120, extra buffer
# probes -100. The guntamatic library only filters some of them.
OPEN_SENSOR_TEMPERATURES = {120.0, -100.0, -20.0}
# status.cgi reports these as fractions (0.32 for 32 %).
STATUS_FRACTIONS = {"co2", "fumes", "fuel"}
ON_OFF_KEYS = re.compile(
    r"^(heating_circulation_pump_\d+|auxiliary_pump_\d+|extra_dhw_boost_\d+"
    r"|dhw_pump_\d+|boiler_shunt_pump)$"
)

# status.cgi field -> (stable key, unit)
STATUS_FIELDS: dict[str, tuple[str, str | None]] = {
    "temp": ("boiler_temperature", "°C"),
    "ext_temp": ("outdoor_temperature", "°C"),
    "co2": ("co2_content", "%"),
    "fumes": ("flue_gas", "%"),
    "fuel": ("fuel_level", "%"),
    # Same counter as the legacy "ash emptying in" line.
    "cleaning_in": ("ash_empty_in", "h"),
    "state": ("status", None),
    "timestamp": ("last_update", None),
}

Value = tuple[Any, str | None]


class _Flag:
    """Remember that something was already logged."""

    def __init__(self) -> None:
        self._set = False

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        self._set = True


_PARSER_FAILED = _Flag()


class _OncePerMessage(logging.Filter):
    """Let each distinct "Untranslated string" warning of the library through once.

    guntamatic logs them on the root logger at every poll, which would flood
    the Home Assistant log once a minute.
    """

    def __init__(self) -> None:
        super().__init__()
        self._seen: set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        if not str(record.msg).startswith("Untranslated string detected"):
            return True
        message = record.getMessage()
        if message in self._seen:
            return False
        if len(self._seen) < 1000:
            self._seen.add(message)
        return True


if not any(isinstance(f, _OncePerMessage) for f in logging.getLogger().filters):
    logging.getLogger().addFilter(_OncePerMessage())


class BiostarError(Exception):
    """Base error for the Biostar client."""


class BiostarConnectionError(BiostarError):
    """The boiler could not be reached or returned no usable data."""


class BiostarCommandError(BiostarError):
    """The boiler refused or did not confirm a write command."""


@dataclass
class HeatingCircuit:
    """Heating circuit as reported by status.cgi."""

    nr: int
    name: str
    day_temp: float | None = None
    night_temp: float | None = None
    program: str | None = None
    # False when status.cgi gave no "nr" and the number is only the list
    # position: good enough to display, never used to write.
    numbered: bool = True


@dataclass
class BiostarData:
    """One poll of the boiler."""

    values: dict[str, Value] = field(default_factory=dict)
    # Legacy values whose label the guntamatic library does not know yet.
    # Keyed by the raw (language dependent) label.
    extras: dict[str, Value] = field(default_factory=dict)
    circuits: dict[int, HeatingCircuit] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # True when status.cgi answered (its error list is then authoritative).
    has_status: bool = False
    meta: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_CONSTRAINTS)
    )


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def coerce_value(value: Any, unit: str | None) -> Any:
    """Convert a raw value to a number when its unit says it is one."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if unit in NUMERIC_UNITS:
        number = _to_float(value)
        return number if number is not None else None
    return value


def normalize_program(value: Any, table: dict[str, str], order: tuple[str, ...]):
    """Return the canonical program name for an index or a localized label."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return order[value] if 0 <= value < len(order) else str(value)
    text = str(value).strip()
    if text.isdigit():
        index = int(text)
        return order[index] if index < len(order) else text
    lowered = text.lower()
    if lowered in order:
        return lowered
    return table.get(lowered, text)


class _OfflineHeater(Heater):
    """guntamatic.Heater fed with data we already downloaded."""

    def __init__(self, raw: dict[str, list[str]]) -> None:
        super().__init__("offline")
        self._raw = raw

    def get_data(self) -> dict[str, list[str]]:
        # parse_data mutates the lists it gets, hand out copies.
        return {key: list(value) for key, value in self._raw.items()}


def _zero_based_fault_lines(raw: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return {interruption_N: entry} for fault lines numbered from 0.

    Firmware 3.x reports "Defaut 0", "Defaut 1" where older firmware reported
    "Defaut 1", "Defaut 2". The guntamatic library maps both "Defaut 0" and
    "Defaut 1" to interruption_1, so the second fault line was lost.
    """
    lines: dict[str, list[str]] = {}
    for label in raw:
        if not label.endswith(" 0") or TRANSLATE.get(label) != "interruption_1":
            continue
        base = label.removesuffix("0")
        nr = 0
        while (entry := raw.get(f"{base}{nr}")) is not None:
            lines[f"interruption_{nr + 1}"] = list(entry)
            nr += 1
    return lines


def parse_legacy(
    descriptions: list[str], values: list[str]
) -> tuple[dict[str, Value], dict[str, Value]]:
    """Parse daqdesc/daqdata lines into (stable values, unknown extras)."""
    raw: dict[str, list[str]] = {}
    for datum, description in zip(values, descriptions):
        if not description or not description.strip():
            continue
        lowered = description.lower()
        if any(word.lower() in lowered for word in (*RESERVED, *EXTRA_RESERVED)):
            continue
        label, *unit = description.split(";")
        label = label.strip()
        if not label:
            continue
        raw[label] = [datum.strip(), "".join(unit).strip()]

    try:
        try:
            parsed = _OfflineHeater(raw).parse_data()
        except NoSerialException:
            # The library insists on a serial number; status.cgi provides it
            # anyway, so parse with a dummy one and drop it afterwards.
            parsed = _OfflineHeater({**raw, SERIAL: ["unknown", ""]}).parse_data()
            parsed.pop("serial", None)
    except Exception:  # noqa: BLE001 - never lose all data to a parser bug
        log = _LOGGER.debug if _PARSER_FAILED.is_set() else _LOGGER.exception
        _PARSER_FAILED.set()
        log("guntamatic library could not parse the legacy data")
        parsed = {}
    parsed.update(_zero_based_fault_lines(raw))

    stable: dict[str, Value] = {}
    for key, (value, unit) in parsed.items():
        unit = unit or None
        value = coerce_value(value, unit)
        if isinstance(value, str) and ON_OFF_KEYS.match(key):
            # Some firmware reports pumps as plain ON/OFF in the boiler
            # language instead of a mode (auto/off/nonstop).
            upper = value.upper()
            if upper in TRUE_VALUES:
                value = "on"
            elif upper in FALSE_VALUES:
                value = "off"
        stable[key] = (value, unit)
    _drop_open_sensors(stable)

    extras: dict[str, Value] = {}
    for label, (value, unit) in raw.items():
        if label in TRANSLATE:
            continue
        unit = unit or None
        upper = value.upper()
        if not unit and upper in TRUE_VALUES:
            extras[label] = (True, None)
        elif not unit and upper in FALSE_VALUES:
            extras[label] = (False, None)
        else:
            extras[label] = (coerce_value(value, unit), unit)
    return stable, extras


def _is_open(values: dict[str, Value], key: str) -> bool:
    entry = values.get(key)
    return (
        entry is not None
        and entry[1] == "°C"
        and isinstance(entry[0], float)
        and entry[0] in OPEN_SENSOR_TEMPERATURES
    )


def _drop_open_sensors(values: dict[str, Value]) -> None:
    """Remove buffer and hot water probes that are not connected."""
    buffer_keys = [
        key
        for key in values
        if re.match(r"^buffer_(top|center|bottom|t\d+)(_\d+)?_temperature$", key)
    ]
    for key in buffer_keys:
        if _is_open(values, key):
            del values[key]
    if not any(re.match(r"^buffer_.*_temperature$", key) for key in values):
        # No buffer probe left: there is no buffer tank to report a load for.
        values.pop("buffer_load", None)

    for nr in range(3):
        if _is_open(values, f"domestic_hot_water_{nr}_temperature"):
            for key in (
                f"domestic_hot_water_{nr}_temperature",
                f"dhw_pump_{nr}",
                f"extra_dhw_{nr}_temperature",
                f"extra_dhw_boost_{nr}",
            ):
                values.pop(key, None)
        elif _is_open(values, f"extra_dhw_{nr}_temperature"):
            values.pop(f"extra_dhw_{nr}_temperature", None)
            values.pop(f"extra_dhw_boost_{nr}", None)


def _circuit_number(circuit: dict[str, Any], index: int) -> tuple[int, bool]:
    """Return (circuit number, whether the boiler stated it explicitly)."""
    try:
        return int(circuit["nr"]), True
    except (KeyError, TypeError, ValueError):
        return index, False


def parse_status(data: dict[str, Any], result: BiostarData) -> None:
    """Fill ``result`` from a status.cgi JSON document."""
    for field_name, (key, unit) in STATUS_FIELDS.items():
        if field_name in data:
            value = coerce_value(data[field_name], unit)
            if (
                field_name in STATUS_FRACTIONS
                and isinstance(value, float)
                and 0.0 <= value <= 1.0
            ):
                value = round(value * 100, 2)
            if value is not None:
                result.values[key] = (value, unit)

    if "mode" in data:
        program = normalize_program(data["mode"], TRANSLATE_PROGRAM, PROGRAMS)
        if program is not None:
            result.values["program"] = (program, None)

    meta = data.get("meta")
    if isinstance(meta, dict):
        result.meta = meta
        if meta.get("sn"):
            result.values["serial"] = (str(meta["sn"]), None)
        if meta.get("sw_version"):
            result.values["version"] = (str(meta["sw_version"]), None)

    constraints = data.get("heat_constraints")
    if isinstance(constraints, dict):
        for name in ("min", "max", "inc"):
            number = _to_float(constraints.get(name))
            if number is not None:
                result.constraints[name] = number

    for index, circuit in enumerate(data.get("heat_circ") or []):
        if not isinstance(circuit, dict):
            continue
        nr, numbered = _circuit_number(circuit, index)
        program = normalize_program(
            circuit.get("mode"), TRANSLATE_HC_PROGRAM, CIRCUIT_PROGRAMS
        )
        result.circuits[nr] = HeatingCircuit(
            nr=nr,
            name=str(circuit.get("name") or f"{nr}"),
            day_temp=_to_float(circuit.get("day_temp")),
            night_temp=_to_float(circuit.get("night_temp")),
            program=program,
            numbered=numbered,
        )
        if program is not None and numbered:
            result.values[f"heating_circulation_program_{nr}"] = (program, None)

    for index, circuit in enumerate(data.get("water_circ") or []):
        if not isinstance(circuit, dict):
            continue
        nr, _numbered = _circuit_number(circuit, index)
        temp = _to_float(circuit.get("temp"))
        if temp is not None and temp not in PLACEHOLDER_TEMPERATURES:
            result.values[f"domestic_hot_water_{nr}_temperature"] = (temp, "°C")

    errors = data.get("error") or []
    if isinstance(errors, list):
        result.errors = [str(error) for error in errors if str(error).strip()]


class BiostarClient:
    """Read and write a Guntamatic Biostar over its local web interface."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        api_key: str,
        write_key: str | None = None,
        include_legacy: bool = True,
    ) -> None:
        self._session = session
        self._host = host.strip()
        self._api_key = api_key
        self._write_key = write_key or None
        self._include_legacy = include_legacy

    @property
    def host(self) -> str:
        return self._host

    @property
    def has_write_access(self) -> bool:
        return bool(self._write_key)

    def _url(self, path: str) -> str:
        return f"http://{self._host}{path}"

    async def _async_get_status(self) -> dict[str, Any] | None:
        try:
            async with self._session.get(
                self._url("/status.cgi"),
                params={"key": self._api_key},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("status.cgi returned HTTP %s", resp.status)
                    return None
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("status.cgi not available: %s", err)
            return None
        if not isinstance(data, dict):
            _LOGGER.debug("status.cgi did not return a JSON object")
            return None
        return data

    async def _async_get_lines(self, path: str) -> list[str]:
        try:
            async with self._session.get(
                self._url(path),
                params={"key": self._api_key},
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    raise BiostarConnectionError(f"{path} returned HTTP {resp.status}")
                text = await resp.text(encoding=ENCODING)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BiostarConnectionError(f"{path} failed: {err}") from err
        return text.splitlines()

    async def async_get_data(self) -> BiostarData:
        """Poll the boiler."""
        result = BiostarData()
        status = await self._async_get_status()
        if status:
            result.has_status = True
            parse_status(status, result)

        if self._include_legacy or not status:
            try:
                descriptions = await self._async_get_lines("/daqdesc.cgi")
                values = await self._async_get_lines("/daqdata.cgi")
            except BiostarConnectionError:
                if not status:
                    raise
                _LOGGER.warning("Legacy endpoints failed, using status.cgi data only")
            else:
                stable, extras = parse_legacy(descriptions, values)
                # status.cgi gives the circuit program as an enum; on firmware
                # 3.3 the legacy line shows a localized state instead
                # ("Chauffage permanent" while status.cgi says "normal").
                status_owned = {
                    f"heating_circulation_program_{nr}"
                    for nr, circuit in result.circuits.items()
                    if circuit.numbered and circuit.program is not None
                }
                # Otherwise the library output is normalised: prefer it over
                # status.cgi unless it has nothing to say (an empty line).
                for key, value in stable.items():
                    if key in status_owned:
                        continue
                    if value[0] is None and key in result.values:
                        continue
                    result.values[key] = value
                result.extras = extras

        if not result.values and not result.circuits:
            raise BiostarConnectionError("The boiler returned no usable data")
        return result

    async def async_get_unique_id(self) -> str:
        """Return the serial number (or the host) for a reachable boiler."""
        status = await self._async_get_status()
        if status is not None:
            meta = status.get("meta")
            serial = meta.get("sn") if isinstance(meta, dict) else None
            return str(serial or "").strip() or self._host
        await self._async_get_lines("/daqdesc.cgi")
        return self._host

    async def _async_send(self, path: str, syn: str, value: str) -> dict | None:
        """Send one parset request. Return the JSON body, None on HTTP 404."""
        params = {"syn": syn, "value": value, "key": self._write_key}
        try:
            async with self._session.get(
                self._url(path), params=params, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    raise BiostarCommandError(f"{path} returned HTTP {resp.status}")
                text = await resp.text(encoding=ENCODING)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise BiostarCommandError(
                f"No answer from the boiler to {syn}={value}, "
                f"the command may or may not have been applied: {err}"
            ) from err

        try:
            body = json.loads(text)
        except ValueError as err:
            raise BiostarCommandError(
                f"Unconfirmed {syn}={value}, unexpected answer: {text.strip()[:100]!r}"
            ) from err
        if not isinstance(body, dict):
            raise BiostarCommandError(
                f"Unconfirmed {syn}={value}, unexpected answer: {body!r}"
            )
        return body

    async def async_set_parameter(self, syn: str, value: str) -> None:
        """Write one boiler parameter and require the boiler to acknowledge it."""
        if not self.has_write_access:
            raise BiostarCommandError("No write key configured")

        body = await self._async_send("/ext/parset.cgi", syn, value)
        if body is None:
            # Older firmware without the /ext/ prefix.
            body = await self._async_send("/parset.cgi", syn, value)
        if body is None:
            raise BiostarCommandError("The boiler has no parset.cgi endpoint")
        if "err" in body:
            raise BiostarCommandError(f"Boiler refused {syn}={value}: {body['err']}")
        if "ack" not in body:
            raise BiostarCommandError(f"Boiler did not confirm {syn}={value}: {body!r}")
        _LOGGER.debug("Boiler acknowledged %s=%s: %s", syn, value, body["ack"])

    async def async_set_program(self, program: str) -> None:
        """Set the boiler program (PR001)."""
        if program not in PROGRAMS:
            raise BiostarCommandError(f"Unknown program {program!r}")
        await self.async_set_parameter("PR001", str(PROGRAMS.index(program)))

    async def async_set_circuit_program(self, circuit: int, program: str) -> None:
        """Set the program of a heating circuit (HKx01)."""
        _check_circuit(circuit)
        if program not in CIRCUIT_PROGRAMS:
            raise BiostarCommandError(f"Unknown circuit program {program!r}")
        await self.async_set_parameter(
            f"HK{circuit}01", str(CIRCUIT_PROGRAMS.index(program))
        )

    async def async_set_circuit_temperature(
        self, circuit: int, period: str, value: float
    ) -> None:
        """Set the day (HKx04) or night (HKx05) room set point of a circuit."""
        _check_circuit(circuit)
        if period not in ("day", "night"):
            raise BiostarCommandError(f"Unknown period {period!r}")
        suffix = "04" if period == "day" else "05"
        await self.async_set_parameter(f"HK{circuit}{suffix}", f"{value:.2f}")


def _check_circuit(circuit: int) -> None:
    if not 0 <= circuit < CIRCUIT_COUNT:
        raise BiostarCommandError(f"Heating circuit {circuit} does not exist")
