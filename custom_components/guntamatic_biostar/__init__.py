"""The GuntamaticBiostar component for controlling the Guntamatic Biostar heating via home assistant / API"""

import logging
from datetime import timedelta
from typing import Any
import json

import async_timeout
from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DATA_SCHEMA_API_KEY, DATA_SCHEMA_HOST, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Guntamatic Biostar from a config entry."""
    websession = async_get_clientsession(hass)
    api_key = entry.data[DATA_SCHEMA_API_KEY]
    host = entry.data[DATA_SCHEMA_HOST]
    coordinator = BiostarUpdateCoordinator(
        hass=hass, session=websession, api_key=api_key, host=host
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Trigger the creation of sensors
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok


class Biostar:
    """API client for Guntamatic Biostar."""

    def __init__(
        self,
        api_key: str,
        host: str,
        session: ClientSession,
    ):
        self._api_key = api_key
        self._host = host
        self._session = session
        self._device_info = None

    async def _async_get_status_data(self) -> dict[str, Any] | None:
        """Try to get data from the modern /status.cgi JSON endpoint."""
        params = {"key": self._api_key}

        try:
            async with self._session.get(
                f"http://{self._host}/status.cgi", params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _LOGGER.debug("Successfully retrieved status.cgi data")
                    return data
                else:
                    _LOGGER.debug(f"status.cgi returned {resp.status}")
                    return None
        except Exception as e:
            _LOGGER.debug(f"status.cgi not available: {e}")
            return None

    async def _async_get_legacy_data(self) -> dict[str, Any]:
        """Get data from legacy /daqdesc.cgi and /daqdata.cgi endpoints."""
        data = {}
        params = {"key": self._api_key}

        legacy_endpoints = ["/daqdesc.cgi", "/daqdata.cgi"]
        dataDescription = None
        dataValues = None

        for API in legacy_endpoints:
            try:
                async with self._session.get(
                    f"http://{self._host}{API}", params=params
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.error(f"Legacy API {API} returned {resp.status}")
                        raise UpdateFailed(f"Legacy API {API} returned {resp.status}")

                    if API == legacy_endpoints[0]:
                        dataDescription = await resp.text(encoding="windows-1252")
                        dataDescription = dataDescription.split("\n")[0:-1]
                    elif API == legacy_endpoints[1]:
                        dataValues = await resp.text(encoding="windows-1252")
                        dataValues = dataValues.split("\n")[0:-1]
            except UpdateFailed:
                raise
            except Exception as e:
                _LOGGER.error(f"Error fetching from legacy API {API}: {e}")
                raise UpdateFailed(f"Failed to fetch from legacy API: {e}")

        # Parse legacy API data
        if dataDescription and dataValues:
            for i in range(min(len(dataDescription), len(dataValues))):
                try:
                    key, unitOfMeasurement = dataDescription[i].split(";")
                except ValueError:
                    continue

                if key.lower() in ["reserved", "réservé", "reserviert"]:
                    continue

                unitOfMeasurement = unitOfMeasurement.strip() or None
                raw_value = dataValues[i].strip()

                # Parse value based on type
                if raw_value in ["AN", "ON", "MARCHE"]:
                    dataValue = True
                elif raw_value in ["AUS", "OFF", "ARRÊT"]:
                    dataValue = False
                elif unitOfMeasurement in ["°C", "%"]:
                    try:
                        dataValue = float(raw_value)
                    except ValueError:
                        dataValue = raw_value
                elif unitOfMeasurement in ["d", "h"]:
                    try:
                        dataValue = int(float(raw_value))
                    except ValueError:
                        dataValue = raw_value
                else:
                    dataValue = raw_value

                data[key] = [dataValue, unitOfMeasurement]

        return data

    async def _async_get_data(self) -> dict[str, Any]:
        """Retrieve data from Guntamatic API.

        Tries the modern /status.cgi first, then enriches with legacy data.
        """
        result = {}

        # Step 1: Try modern JSON API
        status_data = await self._async_get_status_data()

        if status_data:
            # Store device info for later use
            if "meta" in status_data:
                self._device_info = status_data["meta"]

            # Convert status.cgi data to our format
            result = self._parse_status_data(status_data)

        # Step 2: Get legacy data (always, for additional sensors)
        try:
            legacy_data = await self._async_get_legacy_data()

            # Merge legacy data (don't overwrite existing keys from status.cgi)
            for key, value in legacy_data.items():
                if key not in result:
                    result[key] = value

        except UpdateFailed:
            if not result:
                raise
            _LOGGER.warning("Legacy API failed but status.cgi data available")

        _LOGGER.info(f"Biostar: Retrieved {len(result)} sensors")
        _LOGGER.debug(f"Biostar data keys: {list(result.keys())}")

        return result

    def _parse_status_data(self, data: dict) -> dict[str, Any]:
        """Parse /status.cgi JSON data into our sensor format."""
        result = {}

        # Main temperatures and values
        if "temp" in data:
            result["_Température chaudière"] = [data["temp"], "°C"]
        if "ext_temp" in data:
            result["_Température extérieure"] = [data["ext_temp"], "°C"]
        if "co2" in data:
            result["_CO2"] = [data["co2"], "%"]
        if "fumes" in data:
            result["_Fumées"] = [data["fumes"], "%"]
        if "fuel" in data:
            result["_Combustible"] = [data["fuel"], "%"]
        if "cleaning_in" in data:
            result["_Nettoyage dans"] = [data["cleaning_in"], "h"]

        # State/Mode
        if "state" in data:
            result["_État"] = [data["state"], None]
        if "mode" in data:
            result["_Mode"] = [data["mode"], None]
        if "name" in data:
            result["_Nom"] = [data["name"], None]

        # Timestamp
        if "timestamp" in data:
            result["_Dernière mise à jour"] = [data["timestamp"], None]

        # Device info from meta
        if "meta" in data:
            meta = data["meta"]
            if "sw_version" in meta:
                result["_Version firmware"] = [meta["sw_version"], None]
            if "sn" in meta:
                result["_Numéro de série"] = [meta["sn"], None]
            if "typ" in meta:
                result["_Modèle"] = [meta["typ"], None]
            if "language" in meta:
                result["_Langue"] = [meta["language"], None]

        # Heating circuits
        if "heat_circ" in data:
            for i, circuit in enumerate(data["heat_circ"]):
                prefix = f"_Circuit {circuit.get('name', i)}"
                if "day_temp" in circuit:
                    result[f"{prefix} - Temp jour"] = [circuit["day_temp"], "°C"]
                if "night_temp" in circuit:
                    result[f"{prefix} - Temp nuit"] = [circuit["night_temp"], "°C"]
                if "mode" in circuit:
                    result[f"{prefix} - Mode"] = [circuit["mode"], None]

        # Water circuits
        if "water_circ" in data:
            for i, circuit in enumerate(data["water_circ"]):
                prefix = f"_ECS {circuit.get('name', i)}"
                if "temp" in circuit:
                    result[f"{prefix} - Temp"] = [circuit["temp"], "°C"]
                if "mode" in circuit:
                    result[f"{prefix} - Mode"] = [circuit["mode"], None]

        # Errors
        if "error" in data and data["error"]:
            result["_Erreurs actives"] = [len(data["error"]), None]
            for i, error in enumerate(data["error"]):
                result[f"_Erreur {i}"] = [str(error), None]

        return result

    def get_device_info(self) -> dict | None:
        """Return device info from the last API call."""
        return self._device_info


class BiostarUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to manage data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        api_key: str,
        host: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=1),
        )
        self.my_api = Biostar(api_key=api_key, session=session, host=host)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        async with async_timeout.timeout(15):
            return await self.my_api._async_get_data()

    def get_device_info(self) -> dict | None:
        """Get device info from API."""
        return self.my_api.get_device_info()
