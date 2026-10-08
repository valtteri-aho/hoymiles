"""Unit tests for the Hoymiles Cloud config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hoymiles_cloud.client import (
    HoymilesAuthError,
    HoymilesConnectionError,
    StationSummary,
)
from custom_components.hoymiles_cloud.const import DOMAIN


@pytest.mark.asyncio
async def test_flow_user_success_single_station():
    """Test successful user config flow with 1 station auto-detected."""
    from custom_components.hoymiles_cloud.config_flow import HoymilesCloudConfigFlow

    flow = HoymilesCloudConfigFlow()
    flow.hass = AsyncMock()

    mock_station = StationSummary(id=777, name="Home Solar", capacity=1500.0)

    with patch(
        "custom_components.hoymiles_cloud.config_flow.async_get_clientsession"
    ), patch(
        "custom_components.hoymiles_cloud.client.HoymilesCloudClient.async_login",
        AsyncMock(return_value="token123"),
    ), patch(
        "custom_components.hoymiles_cloud.client.HoymilesCloudClient.async_get_stations",
        AsyncMock(return_value=[mock_station]),
    ), patch.object(
        flow, "async_set_unique_id", AsyncMock()
    ), patch.object(
        flow, "_abort_if_unique_id_configured"
    ):
        result = await flow.async_step_user(
            {"username": "user@example.com", "password": "mypassword"}
        )

    assert result["type"] == "create_entry"
    assert result["title"] == "Home Solar"
    assert result["data"]["plant_id"] == 777
    assert result["data"]["username"] == "user@example.com"


@pytest.mark.asyncio
async def test_flow_user_invalid_auth():
    """Test invalid credentials error in config flow."""
    from custom_components.hoymiles_cloud.config_flow import HoymilesCloudConfigFlow

    flow = HoymilesCloudConfigFlow()
    flow.hass = AsyncMock()

    with patch(
        "custom_components.hoymiles_cloud.config_flow.async_get_clientsession"
    ), patch(
        "custom_components.hoymiles_cloud.client.HoymilesCloudClient.async_login",
        AsyncMock(side_effect=HoymilesAuthError("Bad creds")),
    ):
        result = await flow.async_step_user(
            {"username": "user@example.com", "password": "wrongpassword"}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_flow_user_connection_error():
    """Test connection error in config flow."""
    from custom_components.hoymiles_cloud.config_flow import HoymilesCloudConfigFlow

    flow = HoymilesCloudConfigFlow()
    flow.hass = AsyncMock()

    with patch(
        "custom_components.hoymiles_cloud.config_flow.async_get_clientsession"
    ), patch(
        "custom_components.hoymiles_cloud.client.HoymilesCloudClient.async_login",
        AsyncMock(side_effect=HoymilesConnectionError("Timeout")),
    ):
        result = await flow.async_step_user(
            {"username": "user@example.com", "password": "password"}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}

