"""Sample boiler answers used by the tests.

Synthetic data shaped like a French Biostar on firmware 3.2: labels follow the
boiler language, unconnected slots report placeholder temperatures.
"""

from __future__ import annotations

HOST = "192.168.1.165"
API_KEY = "readkey"
WRITE_KEY = "writekey"
BASE = f"http://{HOST}"

# (description line, value line)
LEGACY_LINES: list[tuple[str, str]] = [
    ("fonction; ", "CHAUFFAGE"),
    ("Temp. chaudiere;°C", "65.00"),
    ("temp.exterieure;°C", "7.10"),
    ("charge accu;%", "42"),
    ("accu haut;°C", "61.20"),
    ("réservé;", "0"),
    ("Teneur CO2;%", "11.70"),
    ("Eau chaude 0;°C", "45.50"),
    ("Pompe eau chaude 0;%", "0"),
    # Unconnected hot water slot: placeholder, filtered with its pump.
    ("Eau chaude 1;°C", "-20.00"),
    ("Pompe eau chaude 1;%", "0"),
    # Circuit 0 unconnected (room placeholder 60 °C): whole slot filtered.
    ("temp.amb. CH 0;°C", "60.00"),
    ("aller effect. 0;°C", "44.00"),
    ("Pompe circ.chauf. 0; ", "OFF"),
    ("Programme CH0; ", "OFF"),
    # Circuit 1 connected.
    ("temp.amb. CH 1;°C", "21.50"),
    ("aller effect. 1;°C", "38.00"),
    ("Pompe circ.chauf. 1; ", "DUREE"),
    ("Programme CH1; ", "NORMAL"),
    ("program.; ", "CHAUFFAGE"),
    ("Defaut 1; ", ""),
    ("Série; ", "959103"),
    ("Version; ", "32a"),
    ("Heures de fonctionnemment;h", "1122"),
    ("temps de service;d", "78"),
    # Labels the guntamatic library does not know.
    ("Truc inconnu;°C", "12,5"),
    ("Relais X; ", "MARCHE"),
]

DAQDESC = "\n".join(line for line, _ in LEGACY_LINES).encode("windows-1252")
DAQDATA = "\n".join(value for _, value in LEGACY_LINES).encode("windows-1252")

STATUS = {
    "name": "Biostar",
    "temp": 64.5,
    "ext_temp": 7.0,
    "co2": 11.7,
    "fumes": 59,
    "fuel": 80,
    "cleaning_in": 49,
    "state": "Chauffage",
    "mode": "CHAUFFAGE",
    "meta": {"typ": "Biostar 15", "sn": "959103", "sw_version": "3.2a"},
    "heat_constraints": {"min": 5.0, "max": 30.0, "inc": 0.5},
    "heat_circ": [
        {
            "nr": 1,
            "name": "Maison",
            "day_temp": 21.0,
            "night_temp": 17.0,
            "mode": "NORMAL",
        }
    ],
    "water_circ": [{"nr": 0, "name": "ECS", "temp": 45.0}],
    "error": [],
}


def mock_boiler(aioclient_mock, status=STATUS, legacy=True) -> None:
    """Register the read endpoints on the aiohttp mocker."""
    if status is None:
        aioclient_mock.get(f"{BASE}/status.cgi", status=404)
    else:
        aioclient_mock.get(f"{BASE}/status.cgi", json=status)
    if legacy:
        aioclient_mock.get(f"{BASE}/daqdesc.cgi", content=DAQDESC)
        aioclient_mock.get(f"{BASE}/daqdata.cgi", content=DAQDATA)
    else:
        aioclient_mock.get(f"{BASE}/daqdesc.cgi", status=500)
        aioclient_mock.get(f"{BASE}/daqdata.cgi", status=500)
