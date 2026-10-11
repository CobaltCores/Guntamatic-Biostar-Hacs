"""Fixtures for the Guntamatic Biostar tests."""

from __future__ import annotations

import pytest

from .const import mock_boiler


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


@pytest.fixture
def boiler(aioclient_mock):
    """A French Biostar answering on every read endpoint."""
    mock_boiler(aioclient_mock)
    return aioclient_mock
