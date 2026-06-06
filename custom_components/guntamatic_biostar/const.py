"""The GuntamaticBiostar component for controlling the Guntamatic Biostar heating via home assistant / API"""

from __future__ import annotations


import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfTemperature,
    UnitOfTime,
)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
]

# Global values
DOMAIN = "guntamatic_biostar"
MANUFACTURER = "Guntamatic"
MODEL = "Biostar"
DATA_SCHEMA_HOST = "host"
DATA_SCHEMA_API_KEY = "api_key"
DATA_SCHEMA_WRITE_KEY = "write_key"
CONF_INCLUDE_LEGACY = "include_legacy_sensors"
DEFAULT_INCLUDE_LEGACY = True
OLD_DYNAMIC_ENTITY_UNIQUE_ID_PREFIX = "biostar_"

# Data schema required by configuration flow
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(DATA_SCHEMA_HOST): cv.string,
        vol.Required(DATA_SCHEMA_API_KEY): cv.string,
        vol.Optional(DATA_SCHEMA_WRITE_KEY): cv.string,
    }
)

# Program options for heating control (write access required)
PROGRAM_OPTIONS = {
    "off": 0,
    "normal": 1,
    "heat": 2,
    "lower": 3,
}
PROGRAM_OPTIONS_REVERSE = {v: k for k, v in PROGRAM_OPTIONS.items()}


# Unit to device class mapping for dynamic sensor creation
UNIT_DEVICE_CLASS_MAP = {
    "°C": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "%": {
        "device_class": None,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "h": {
        "device_class": None,
        "unit": UnitOfTime.HOURS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "d": {
        "device_class": None,
        "unit": UnitOfTime.DAYS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
}

TOTAL_INCREASING_KEYWORDS = [
    "betrieb",
    "fonction",
    "function",
    "runtime",
]

COUNTDOWN_KEYWORDS = [
    "cleaning_in",
    "dans",
    "left",
    "nettoyage",
    "remaining",
    "restant",
]

PROGRAM_STATE_KEYS = [
    "_mode",
    "_program",
    "_programme",
    "mode",
    "program",
    "programme",
    "prog",
]

PROGRAM_OPTION_ALIASES = {
    "off": ["off", "aus", "arret", "arrêt", "stop"],
    "normal": ["normal", "standard"],
    "heat": ["heat", "heating", "chauffage", "chauffe", "heizen"],
    "lower": ["lower", "reduit", "réduit", "abaisse", "absenk", "eco", "night"],
}

# Keywords to identify sensor icons (works across languages)
ICON_KEYWORDS = {
    # Temperature related
    "ext": "mdi:sun-thermometer-outline",  # extérieure, external, außen
    "chaud": "mdi:fire",  # chaudière, kessel, boiler
    "kessel": "mdi:fire",
    "boiler": "mdi:fire",
    # Buffer/accumulator
    "accu": "mdi:water-boiler",
    "puff": "mdi:water-boiler",
    "tamp": "mdi:water-boiler",
    "buffer": "mdi:water-boiler",
    # Hot water
    "ecs": "mdi:water-boiler",
    "warmwasser": "mdi:water-boiler",
    "hot water": "mdi:water-boiler",
    # Pumps
    "pump": "mdi:pump",
    "pomp": "mdi:pump",
    # Heating circuits
    "circ": "mdi:heating-coil",
    "heiz": "mdi:heating-coil",
    # Fans
    "vent": "mdi:fan",
    "gebl": "mdi:fan",
    "fan": "mdi:fan",
    # Motors
    "mot": "mdi:cog",
    "motor": "mdi:cog",
    # Maintenance
    "cendr": "mdi:delete-empty",
    "asche": "mdi:delete-empty",
    "ash": "mdi:delete-empty",
    "révis": "mdi:account-wrench",
    "service": "mdi:account-wrench",
    # Time
    "fonct": "mdi:counter",
    "betrieb": "mdi:counter",
    "runtime": "mdi:counter",
    # Defaults
    "defaut": "mdi:alert-circle",
    "störung": "mdi:alert-circle",
    "error": "mdi:alert-circle",
    "fault": "mdi:alert-circle",
    # Program
    "program": "mdi:cog",
    "prog": "mdi:cog",
}

# Keys that should be treated as diagnostic (hidden by default)
DIAGNOSTIC_KEYWORDS = [
    "version",
    "série",
    "serial",
    "defaut",
    "störung",
    "error",
    "fault",
    "fonction",
    "betrieb",
    "function",
]

# Keys to exclude (reserved, empty, etc.)
EXCLUDE_KEYWORDS = ["réservé", "reserved", "reserviert"]


def get_icon_for_key(key: str) -> str:
    """Get an appropriate icon based on the sensor key."""
    key_lower = key.lower()
    for keyword, icon in ICON_KEYWORDS.items():
        if keyword in key_lower:
            return icon
    return "mdi:gauge"


def is_diagnostic_sensor(key: str) -> bool:
    """Check if a sensor should be marked as diagnostic."""
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in DIAGNOSTIC_KEYWORDS)


def should_exclude_key(key: str) -> bool:
    """Check if a key should be excluded from sensor creation."""
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in EXCLUDE_KEYWORDS)


def get_sensor_metadata(key: str, unit: str | None) -> dict | None:
    """Return HA metadata for a sensor key/unit pair."""
    if unit not in UNIT_DEVICE_CLASS_MAP:
        return None

    metadata = dict(UNIT_DEVICE_CLASS_MAP[unit])
    key_lower = key.lower()

    if unit in {"h", "d"}:
        if any(keyword in key_lower for keyword in TOTAL_INCREASING_KEYWORDS):
            metadata["state_class"] = SensorStateClass.TOTAL_INCREASING
        elif any(keyword in key_lower for keyword in COUNTDOWN_KEYWORDS):
            metadata["state_class"] = SensorStateClass.MEASUREMENT

    return metadata


def normalize_program_option(value) -> str | None:
    """Normalize a raw boiler program value to a select option."""
    if isinstance(value, int) and value in PROGRAM_OPTIONS_REVERSE:
        return PROGRAM_OPTIONS_REVERSE[value]

    if not isinstance(value, str):
        return None

    value_lower = value.lower()
    for option, aliases in PROGRAM_OPTION_ALIASES.items():
        if any(alias in value_lower for alias in aliases):
            return option

    return None


def is_program_state_key(key: str) -> bool:
    """Return true if a data key is a likely heating program key."""
    key_lower = key.lower().lstrip("_")
    return key_lower in PROGRAM_STATE_KEYS
