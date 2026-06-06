"""Tests for the Guntamatic Biostar API client."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import pytest

from custom_components.guntamatic_biostar import Biostar


class FakeResponse:
    """Minimal aiohttp response test double."""

    def __init__(
        self,
        *,
        status: int = 200,
        json_data=None,
        text_data: str = "",
    ) -> None:
        """Initialize response."""
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def __aenter__(self):
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """Exit async context manager."""
        return False

    async def json(self, content_type=None):
        """Return JSON data."""
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    async def text(self, encoding=None):
        """Return text data."""
        return self._text_data


class FakeSession:
    """Minimal aiohttp session test double."""

    def __init__(self, responses: dict[str, FakeResponse]) -> None:
        """Initialize session."""
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **kwargs):
        """Return a configured response by URL path."""
        path = urlsplit(url).path
        self.calls.append(path)
        return self.responses[path]


def _get_data(client: Biostar):
    return asyncio.run(client._async_get_data())


def test_status_only_skips_legacy_when_disabled():
    """Test modern JSON API can run without legacy enrichment."""
    session = FakeSession(
        {
            "/status.cgi": FakeResponse(
                json_data={
                    "temp": 65.2,
                    "cleaning_in": 12,
                    "meta": {
                        "typ": "Biostar 15",
                        "sn": "SN123",
                        "sw_version": "4.0",
                    },
                }
            )
        }
    )
    client = Biostar("api-key", "boiler.local", session, include_legacy=False)

    data = _get_data(client)

    assert data["_Température chaudière"] == [65.2, "°C"]
    assert data["_Nettoyage dans"] == [12, "h"]
    assert client.get_device_info()["sn"] == "SN123"
    assert session.calls == ["/status.cgi"]


def test_legacy_enrichment_merges_without_overwriting_status_data():
    """Test legacy data is parsed and merged after status.cgi."""
    session = FakeSession(
        {
            "/status.cgi": FakeResponse(json_data={"temp": 65.2}),
            "/daqdesc.cgi": FakeResponse(
                text_data="Température chaudière;°C\nPompe;\nReserved;h\n"
            ),
            "/daqdata.cgi": FakeResponse(text_data="62.0\nAN\n999\n"),
        }
    )
    client = Biostar("api-key", "boiler.local", session, include_legacy=True)

    data = _get_data(client)

    assert data["_Température chaudière"] == [65.2, "°C"]
    assert data["Température chaudière"] == [62.0, "°C"]
    assert data["Pompe"] == [True, None]
    assert "Reserved" not in data
    assert session.calls == ["/status.cgi", "/daqdesc.cgi", "/daqdata.cgi"]


def test_legacy_fallback_runs_when_status_is_unavailable_even_if_disabled():
    """Test legacy endpoints are fallback when status.cgi fails."""
    session = FakeSession(
        {
            "/status.cgi": FakeResponse(status=404),
            "/daqdesc.cgi": FakeResponse(text_data="Température;°C\n"),
            "/daqdata.cgi": FakeResponse(text_data="21.5\n"),
        }
    )
    client = Biostar("api-key", "boiler.local", session, include_legacy=False)

    data = _get_data(client)

    assert data["Température"] == [21.5, "°C"]
    assert session.calls == ["/status.cgi", "/daqdesc.cgi", "/daqdata.cgi"]


def test_legacy_failure_without_status_data_raises_update_failed():
    """Test total API failure raises coordinator update failure."""
    session = FakeSession(
        {
            "/status.cgi": FakeResponse(status=404),
            "/daqdesc.cgi": FakeResponse(status=500),
        }
    )
    client = Biostar("api-key", "boiler.local", session, include_legacy=False)

    with pytest.raises(Exception):
        _get_data(client)
