# Guntamatic Biostar for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/CobaltCores/Guntamatic-Biostar-Hacs?style=for-the-badge&color=blue)](https://github.com/CobaltCores/Guntamatic-Biostar-Hacs/releases)

Integration for **Guntamatic Biostar** biomass boilers in Home Assistant.

This custom component communicates directly with your boiler's local API to retrieve real-time status, temperatures, and diagnostic data.

## ✨ Features

- **🚀 Auto-Discovery**: Automatically detects all available sensors from your boiler.
- **🌍 Multi-Language Support**: Works with any boiler language (FR, DE, EN, etc.). Sensor names are dynamically retrieved from the boiler.
- **📊 Rich Data**: Uses the modern `/status.cgi` JSON endpoint for structured data:
  - Temperatures (Boiler, Outside, Buffer, DHW)
  - Heating Circuits statuses
  - Diagnostic data (CO2, Fan speeds, Maintenance counters)
  - Device Info (Serial Number, Firmware Version)
- **⚡ Fast Updates**: Polls data every minute.
- **🔧 Easy Config**: Fully configurable via the Home Assistant UI.

## 📦 Installation

### Option 1: HACS (Recommended)

1. Open HACS in Home Assistant.
2. Click on **Integrations** > **Three dots menu** > **Custom repositories**.
3. Add `https://github.com/CobaltCores/Guntamatic-Biostar-Hacs` as an **Integration**.
4. Click **Download**.
5. Restart Home Assistant.

### Option 2: Manual

1. Download the latest release.
2. Copy the `custom_components/GuntamaticBiostar` folder to your HA `custom_components` directory.
3. Restart Home Assistant.

## ⚙️ Configuration

1. Go to **Settings** > **Devices & Services**.
2. Click **+ ADD INTEGRATION**.
3. Search for **Guntamatic Biostar**.
4. Enter your boiler's details:
   - **Host**: IP address of the boiler (e.g., `192.168.1.165`)
   - **API Key**: Your Guntamatic API key (usually found on the boiler's sticker or in the menu)

## 🔍 How it works

The integration intelligently queries multiple endpoints:

1. **`/status.cgi` (JSON)**: Prefered method. Retrieves structured data, device info, and heating circuits.
2. **`/daqdesc.cgi` & `/daqdata.cgi` (Legacy)**: Fallback method. Retrieves raw sensor values if JSON is missing.
3. **`/ext/` endpoints**: Checks for extended data on older firmware versions.

## 🐛 Troubleshooting

If sensors show as "Unavailable":

- Check if your boiler IP has changed.
- Verify your API key is correct.
- Ensure the boiler is powered on and connected to the network.
- Enable debug logging to see what the API returns in your HA logs.

## ❤️ Credits

Based on the work of [@a529987659852](https://github.com/a529987659852) (original author).
Maintained by [@CobaltCores](https://github.com/CobaltCores).
