# Guntamatic Biostar for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/CobaltCores/Guntamatic-Biostar-Hacs?style=for-the-badge&color=blue)](https://github.com/CobaltCores/Guntamatic-Biostar-Hacs/releases)

Integration for **Guntamatic Biostar** biomass boilers in Home Assistant, talking to the boiler's local web interface.

> **Read-only use?** Since Home Assistant 2026.6 there is an official [Guntamatic integration](https://www.home-assistant.io/integrations/guntamatic/) that needs no API key. This custom integration adds what it does not cover: the `status.cgi` data (heating circuits, set points, errors, fuel, flue gas) and **control** of the boiler program, circuit programs and room set points with a write key.

## ✨ Features

- **Stable entities in every boiler language**: values are identified by fixed English keys, so changing the boiler language or a firmware update that renames labels (as 3.3 did) keeps your entities and history. The legacy endpoints are parsed with the [`guntamatic`](https://github.com/JensTimmerman/guntamatic) library, the same one the official integration uses.
- **No ghost sensors**: unconnected heating circuits, hot water slots and buffer stages report placeholder temperatures (-20, -9, 60 °C); they are not turned into entities.
- **No duplicates**: a value reported by both `status.cgi` and the legacy endpoints is exposed once.
- **Translated names** (English and French; other languages fall back to English for sensor names).
- **Control** (write key needed):
  - boiler program: off, normal, hot water only, heating, reduced, reduced until, hot water boost;
  - program of each heating circuit: off, normal, heating, reduced, reduced until;
  - day and night room set point of each heating circuit.
  Every command must be acknowledged by the boiler; a refused command shows an error in Home Assistant, and a value the boiler acknowledges but does not report on the next poll is logged as a warning.
- **Fault binary sensor** with the active fault messages as an attribute.

## 📦 Installation

### Option 1: HACS (Recommended)

1. Open HACS in Home Assistant.
2. Click on **Integrations** > **Three dots menu** > **Custom repositories**.
3. Add `https://github.com/CobaltCores/Guntamatic-Biostar-Hacs` as an **Integration**.
4. Click **Download**.
5. Restart Home Assistant.

### Option 2: Manual

1. Download the latest release.
2. Copy the `custom_components/guntamatic_biostar` folder to your HA `custom_components` directory.
3. Restart Home Assistant.

Requires Home Assistant 2025.3 or newer.

## ⚙️ Configuration

1. Go to **Settings** > **Devices & Services**.
2. Click **+ ADD INTEGRATION**.
3. Search for **Guntamatic Biostar**.
4. Enter your boiler's details:
   - **Host**: IP address of the boiler (e.g., `192.168.1.165`)
   - **API Key**: Your Guntamatic API key (from Guntamatic support)
   - **Write Key**: Optional, only required for changing programs or set points.

### Options

Open the integration options from **Settings** > **Devices & Services** to choose whether Home Assistant should also query the legacy endpoints. They provide most sensors (buffer, pumps, fans, room and flow temperatures, counters); keep them enabled unless you only need the `status.cgi` values.

## 🔍 How it works

| Endpoint | Used for |
| --- | --- |
| `/status.cgi` (JSON, API key) | device info, heating circuits and set points, program, errors, fuel, flue gas, cleaning countdown |
| `/daqdesc.cgi` + `/daqdata.cgi` | most sensors, normalised by the `guntamatic` library |
| `/ext/parset.cgi` (write key) | commands, `/parset.cgi` on firmware without `/ext/` |

Commands use the boiler's own parameter IDs (from its `par.cgi` parameter table):

| Parameter | Meaning | Values |
| --- | --- | --- |
| `PR001` | boiler program | 0 off, 1 normal, 2 hot water, 3 heating, 4 reduced, 5 reduced until, 6 hot water boost |
| `HKx01` | program of circuit x | 0 off, 1 normal, 2 heating, 3 reduced, 4 reduced until |
| `HKx04` | day set point of circuit x | 5 – 30 °C, step 0.5 |
| `HKx05` | night set point of circuit x | 5 – 30 °C, step 0.5 |

`x` is the circuit number as shown on the boiler (0 – 8), taken from the `nr` field of `status.cgi`; circuits without an explicit `nr` get no controls. The enum order comes from a firmware 3.2 parameter table; other models may differ (openHAB uses 8 for a manual program), hence the check after each write.

Values the `guntamatic` library does not know yet are still created, under their boiler label, but disabled by default because their name depends on the boiler language. If you see one, please report it upstream so it gets a stable key.

## ⬆️ Upgrading from 1.x

- Sensors are migrated to the stable keys automatically: entity IDs, history, dashboards and automations keep working. This covers every legacy sensor and the main `status.cgi` values (boiler and outdoor temperature, CO₂, flue gas, fuel, cleaning countdown, state, mode, firmware, serial, last update).
- Values that 1.x exposed twice (from `status.cgi` and from the legacy endpoints) are now exposed once. The enabled entity takes over (the legacy one if both are enabled); the other one stops updating and a warning in the log names both. Delete it once nothing uses it.
- Not migrated, they stop updating and can be deleted: the per-circuit `status.cgi` sensors (`Circuit … - Temp jour/nuit/Mode`), `ECS … - Temp`, `Erreur N`, `Erreurs actives`, `Nom`, `Modèle`, `Langue`, sensors for unconnected slots, and, with a write key, the program sensors (the select entities show the program).
- Binary sensors created from on/off legacy values are replaced by sensors (pump states `on`/`off` or modes `auto`/`off`/`nonstop`) and by the new fault sensor.
- **The program select sent wrong values in 1.x**: "heat" switched the boiler to hot water only and "lower" to heating. The options are now the boiler's own list (`normal` is `timer`, `lower` is `hibernate`). Update automations that set the program.
- **1.x wrote the day/night set points to the wrong parameters** (`HK(x+1)02` / `HK(x+1)03`, the pump mode and timer program of the next circuit). If you changed set points from Home Assistant, check the pump mode and timer program of your heating circuits on the boiler.

## 🐛 Troubleshooting

If sensors show as "Unavailable":

- Check if your boiler IP has changed.
- Verify your API key is correct.
- Ensure the boiler is powered on and connected to the network.
- Enable debug logging to see what the API returns in your HA logs.

## 🧪 Development

```bash
pip install -r requirements_test.txt
pytest
```

## ❤️ Credits

Based on the work of [@a529987659852](https://github.com/a529987659852) (original author).
Legacy parsing by the [`guntamatic`](https://github.com/JensTimmerman/guntamatic) library of [@JensTimmerman](https://github.com/JensTimmerman).
Maintained by [@CobaltCores](https://github.com/CobaltCores).
