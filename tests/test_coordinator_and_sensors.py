"""Unit tests for coordinator and sensor platforms."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.hoymiles_cloud.client import (
    MicroInverterInfo,
    PlantDevices,
    StationRealData,
)
from custom_components.hoymiles_cloud.coordinator import (
    HoymilesDataUpdateCoordinator,
    MicroInverterState,
)
from custom_components.hoymiles_cloud.sensor import (
    PLANT_SENSOR_DESCRIPTIONS,
    HoymilesMicroAlarmCodeSensor,
    HoymilesMicroAlarmMsgSensor,
    HoymilesPlantSensor,
)
from custom_components.hoymiles_cloud.binary_sensor import (
    HoymilesMicroConnectedBinarySensor,
    HoymilesMicroProblemBinarySensor,
    HoymilesPlantProducingBinarySensor,
)


@pytest.fixture
def mock_client():
    """Create a mock HoymilesCloudClient."""
    client = MagicMock()
    client.async_get_real_data = AsyncMock(
        return_value=StationRealData(
            station_id=1001,
            real_power_w=1250.0,
            today_energy_kwh=4.5,
            month_energy_kwh=88.0,
            total_energy_kwh=2150.0,
            co2_reduction_kg=1.8,
            tree_planted=3.2,
        )
    )

    micro = MicroInverterInfo(
        id=2002,
        sn="114170009999",
        model="HMS-800",
        firmware_version="V1.0",
        connected=True,
    )
    client.async_get_devices = AsyncMock(
        return_value=PlantDevices(station_id=1001, micro_inverters=[micro])
    )
    client.async_get_micro_details = AsyncMock(
        return_value=(True, 0, "")
    )
    return client


@pytest.mark.asyncio
async def test_coordinator_update_data(mock_client):
    """Test coordinator data retrieval and structure."""
    hass = MagicMock()
    coordinator = HoymilesDataUpdateCoordinator(
        hass=hass,
        client=mock_client,
        plant_id=1001,
        plant_name="My Solar Plant",
        update_interval_seconds=300,
    )

    data = await coordinator._async_update_data()

    assert data.plant_id == 1001
    assert data.plant_name == "My Solar Plant"
    assert data.real_data.real_power_w == 1250.0
    assert 2002 in data.micro_inverters
    micro_state = data.micro_inverters[2002]
    assert micro_state.info.model == "HMS-800"
    assert micro_state.connected is True
    assert micro_state.alarm_code == 0


def test_plant_sensors(mock_client):
    """Test plant-level sensor entity readings."""
    coordinator = MagicMock()
    coordinator.plant_id = 1001
    coordinator.plant_name = "My Solar Plant"
    coordinator.data.real_data = StationRealData(
        station_id=1001,
        real_power_w=1250.0,
        today_energy_kwh=4.5,
        month_energy_kwh=88.0,
        total_energy_kwh=2150.0,
        co2_reduction_kg=1.8,
        tree_planted=3.2,
    )

    power_desc = next(d for d in PLANT_SENSOR_DESCRIPTIONS if d.key == "real_power")
    power_sensor = HoymilesPlantSensor(coordinator, power_desc)
    assert power_sensor.native_value == 1250.0

    today_desc = next(d for d in PLANT_SENSOR_DESCRIPTIONS if d.key == "today_energy")
    today_sensor = HoymilesPlantSensor(coordinator, today_desc)
    assert today_sensor.native_value == 4.5

    total_desc = next(d for d in PLANT_SENSOR_DESCRIPTIONS if d.key == "total_energy")
    total_sensor = HoymilesPlantSensor(coordinator, total_desc)
    assert total_sensor.native_value == 2150.0


def test_micro_sensors_and_binary_sensors():
    """Test micro-inverter diagnostic entities."""
    coordinator = MagicMock()
    coordinator.plant_id = 1001
    coordinator.data.real_data.real_power_w = 1250.0

    micro_info = MicroInverterInfo(
        id=2002,
        sn="114170009999",
        model="HMS-800",
        firmware_version="V1.0",
        has_warning=False,
    )
    coordinator.data.micro_inverters = {
        2002: MicroInverterState(
            info=micro_info,
            connected=True,
            alarm_code=102,
            alarm_message="Grid Overvoltage",
        )
    }

    # Sensor entities
    code_sensor = HoymilesMicroAlarmCodeSensor(coordinator, 2002)
    assert code_sensor.native_value == 102

    msg_sensor = HoymilesMicroAlarmMsgSensor(coordinator, 2002)
    assert msg_sensor.native_value == "Grid Overvoltage"

    # Binary sensors
    generating_sensor = HoymilesPlantProducingBinarySensor(coordinator)
    assert generating_sensor.is_on is True

    connected_sensor = HoymilesMicroConnectedBinarySensor(coordinator, 2002)
    assert connected_sensor.is_on is True

    problem_sensor = HoymilesMicroProblemBinarySensor(coordinator, 2002)
    assert problem_sensor.is_on is True
