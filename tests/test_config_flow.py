"""Tests for the Guntamatic Biostar config and options flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.guntamatic_biostar.const import CONF_INCLUDE_LEGACY, DOMAIN

from .const import API_KEY, BASE, HOST, mock_boiler

USER_INPUT = {"host": f" {HOST} ", "api_key": API_KEY}


async def test_user_flow_uses_serial_as_unique_id(hass: HomeAssistant, boiler):
    """A reachable boiler is identified by its serial number."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "959103"
    assert result["data"]["host"] == HOST
    assert result["options"] == {CONF_INCLUDE_LEGACY: True}


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock):
    """An unreachable boiler shows an error."""
    aioclient_mock.get(f"{BASE}/status.cgi", status=401)
    aioclient_mock.get(f"{BASE}/daqdesc.cgi", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_legacy_only(hass: HomeAssistant, aioclient_mock):
    """Without status.cgi the host identifies the boiler."""
    mock_boiler(aioclient_mock, status=None)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == HOST


async def test_user_flow_already_configured(hass: HomeAssistant, boiler):
    """The same boiler cannot be added twice."""
    MockConfigEntry(
        domain=DOMAIN, unique_id="959103", data={"host": "10.0.0.2"}
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, boiler):
    """The legacy endpoints can be switched off."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="959103",
        version=3,
        data={"host": HOST, "api_key": API_KEY},
        options={CONF_INCLUDE_LEGACY: True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_INCLUDE_LEGACY: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_INCLUDE_LEGACY: False}
