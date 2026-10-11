"""Constants for the Guntamatic Biostar integration."""

from __future__ import annotations

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import Platform

DOMAIN = "guntamatic_biostar"
MANUFACTURER = "Guntamatic"
MODEL = "Biostar"

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
]

DATA_SCHEMA_HOST = "host"
DATA_SCHEMA_API_KEY = "api_key"
DATA_SCHEMA_WRITE_KEY = "write_key"
CONF_INCLUDE_LEGACY = "include_legacy_sensors"
DEFAULT_INCLUDE_LEGACY = True

UPDATE_INTERVAL_SECONDS = 60

# Version 1 used "biostar_<label>" unique IDs, version 2 "<entry>_<label>"
# with the language dependent label, version 3 "<entry>_<stable key>".
CONFIG_ENTRY_VERSION = 3
OLD_DYNAMIC_ENTITY_UNIQUE_ID_PREFIX = "biostar_"

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(DATA_SCHEMA_HOST): cv.string,
        vol.Required(DATA_SCHEMA_API_KEY): cv.string,
        vol.Optional(DATA_SCHEMA_WRITE_KEY): cv.string,
    }
)

# Labels the 1.x releases gave to status.cgi values, mapped to the stable keys
# used since 2.0. Only needed to migrate existing entities.
LEGACY_STATUS_LABELS = {
    "_Température chaudière": "boiler_temperature",
    "_Température extérieure": "outdoor_temperature",
    "_CO2": "co2_content",
    "_Fumées": "flue_gas",
    "_Combustible": "fuel_level",
    "_Nettoyage dans": "cleaning_countdown",
    "_État": "status",
    "_Mode": "program",
    "_Version firmware": "version",
    "_Numéro de série": "serial",
    "_Dernière mise à jour": "last_update",
}
