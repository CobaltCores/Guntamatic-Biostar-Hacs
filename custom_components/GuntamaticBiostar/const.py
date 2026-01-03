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
]

# Global values
DOMAIN = "GuntamaticBiostar"
MANUFACTURER = "Guntamatic"
MODEL = "Biostar"
DATA_SCHEMA_HOST = "host"
DATA_SCHEMA_API_KEY = "api_key"

# Data schema required by configuration flow
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(DATA_SCHEMA_HOST): cv.string,
        vol.Required(DATA_SCHEMA_API_KEY): cv.string,
    }
)


# Unit to device class mapping for dynamic sensor creation
UNIT_DEVICE_CLASS_MAP = {
    "°C": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "unit": UnitOfTemperature.CELSIUS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "%": {
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "unit": PERCENTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "h": {
        "device_class": None,
        "unit": UnitOfTime.HOURS,
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    "d": {
        "device_class": None,
        "unit": UnitOfTime.DAYS,
        "state_class": SensorStateClass.MEASUREMENT,
    },
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
