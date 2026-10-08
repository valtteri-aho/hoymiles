"""Unit tests for the asynchronous Hoymiles Cloud API client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from custom_components.hoymiles_cloud.client import (
    HoymilesApiError,
    HoymilesAuthError,
    HoymilesCloudClient,
    HoymilesConnectionError,
    MicroInverterInfo,
    StationRealData,
    StationSummary,
)


@pytest.fixture
def client():
    """Create a client instance for testing."""
    return HoymilesCloudClient(username="test_user", password="secret_password")


@pytest.mark.asyncio
async def test_legacy_login_success(client):
    """Test legacy MD5 login flow."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={"status": "0", "data": {"token": "test_legacy_token_123"}}
    )

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    mock_session.closed = False

    client._session = mock_session

    with patch.object(client, "_async_argon_login", return_value=None):
        token = await client.async_login()

    assert token == "test_legacy_token_123"
    assert client.token == "test_legacy_token_123"
    assert client.api_version == "0"


@pytest.mark.asyncio
async def test_argon_login_success(client):
    """Test modern Argon2 challenge-response flow."""
    with patch(
        "custom_components.hoymiles_cloud.client.ARGON2_AVAILABLE", True
    ), patch.object(
        client, "_argon_compute_challenge", return_value="computed_challenge_hash"
    ):
        mock_pre_insp = AsyncMock()
        mock_pre_insp.status = 200
        mock_pre_insp.json = AsyncMock(
            return_value={"status": "0", "data": {"n": "nonce123", "a": "aabbcc"}}
        )

        mock_login = AsyncMock()
        mock_login.status = 200
        mock_login.json = AsyncMock(
            return_value={"status": "0", "data": {"token": "argon_token_xyz"}}
        )

        mock_session = MagicMock()
        mock_session.post.return_value.__aenter__.side_effect = [
            mock_pre_insp,
            mock_login,
        ]
        mock_session.closed = False
        client._session = mock_session

        token = await client.async_login()

    assert token == "argon_token_xyz"
    assert client.token == "argon_token_xyz"
    assert client.api_version == "1"


@pytest.mark.asyncio
async def test_login_failure_raises_auth_error(client):
    """Test that failed authentication raises HoymilesAuthError."""
    with patch.object(client, "_async_argon_login", return_value=None), patch.object(
        client, "_async_legacy_login", return_value=None
    ):
        with pytest.raises(HoymilesAuthError):
            await client.async_login()


@pytest.mark.asyncio
async def test_get_stations(client):
    """Test station listing."""
    client.token = "valid_token"
    mock_resp_data = {
        "status": "0",
        "data": {
            "list": [
                {
                    "id": 12345,
                    "station_name": "My Solar Roof",
                    "capacity": 2400.0,
                    "status": 1,
                    "timezone": "Europe/Helsinki",
                }
            ]
        },
    }

    with patch.object(client, "_request", return_value=mock_resp_data):
        stations = await client.async_get_stations()

    assert len(stations) == 1
    assert isinstance(stations[0], StationSummary)
    assert stations[0].id == 12345
    assert stations[0].name == "My Solar Roof"
    assert stations[0].capacity == 2400.0


@pytest.mark.asyncio
async def test_get_real_data(client):
    """Test fetching real-time metrics for a station."""
    client.token = "valid_token"
    mock_resp_data = {
        "status": "0",
        "data": {
            "real_power": 1850.5,
            "today_eq": 8.42,
            "month_eq": 150.2,
            "total_eq": 3200.0,
            "co2_emission_reduction": 2.1,
            "plant_tree": 4,
            "data_time": "2026-10-08 12:00:00",
        },
    }

    with patch.object(client, "_request", return_value=mock_resp_data):
        real_data = await client.async_get_real_data(12345)

    assert isinstance(real_data, StationRealData)
    assert real_data.station_id == 12345
    assert real_data.real_power_w == 1850.5
    assert real_data.today_energy_kwh == 8.42
    assert real_data.total_energy_kwh == 3200.0
    assert real_data.co2_reduction_kg == 2.1


@pytest.mark.asyncio
async def test_get_devices(client):
    """Test parsing hardware tree into micro-inverters."""
    client.token = "valid_token"
    mock_tree = {
        "status": "0",
        "data": [
            {
                "id": 101,
                "text": "DTU-W100",
                "type": 1,
                "children": [
                    {
                        "id": 202,
                        "sn": "114172345678",
                        "model_no": "HM-800",
                        "soft_ver": "V01.00.12",
                        "type": 3,
                        "warn_data": {"connect": True, "warn": False},
                        "children": [],
                    }
                ],
            }
        ],
    }

    with patch.object(client, "_request", return_value=mock_tree):
        devices = await client.async_get_devices(12345)

    assert len(devices.micro_inverters) == 1
    micro = devices.micro_inverters[0]
    assert isinstance(micro, MicroInverterInfo)
    assert micro.id == 202
    assert micro.sn == "114172345678"
    assert micro.model == "HM-800"
    assert micro.connected is True
    assert micro.has_warning is False


@pytest.mark.asyncio
async def test_token_expiration_retry(client):
    """Test that status 100 triggers re-login and retries request."""
    client.token = "expired_token"

    mock_resp_expired = AsyncMock()
    mock_resp_expired.status = 200
    mock_resp_expired.json = AsyncMock(
        return_value={"status": "100", "message": "Token expired"}
    )

    mock_resp_success = AsyncMock()
    mock_resp_success.status = 200
    mock_resp_success.json = AsyncMock(
        return_value={"status": "0", "data": {"real_power": 500}}
    )

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__.side_effect = [
        mock_resp_expired,
        mock_resp_success,
    ]
    mock_session.closed = False
    client._session = mock_session

    with patch.object(client, "async_login", AsyncMock(return_value="new_fresh_token")):
        res = await client._request("test/endpoint", {})

    assert res.get("status") == "0"
    assert res.get("data", {}).get("real_power") == 500

