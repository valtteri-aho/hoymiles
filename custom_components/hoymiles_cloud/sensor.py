"""Sensor platform for Hoymiles Solar Cloud integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    HoymilesCoordinatorData,
    HoymilesDataUpdateCoordinator,
    MicroInverterState,
)


@dataclass(frozen=True, kw_only=True)
class HoymilesPlantSensorDescription(SensorEntityDescription):
    """Description for plant-level sensors."""

    value_fn: Callable[[HoymilesCoordinatorData], Any]


PLANT_SENSOR_DESCRIPTIONS: tuple[HoymilesPlantSensorDescription, ...] = (
    HoymilesPlantSensorDescription(
        key="real_power",
        name="Current Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
        value_fn=lambda data: data.real_data.real_power_w,
    ),
    HoymilesPlantSensorDescription(
        key="today_energy",
        name="Today Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power-variant",
        value_fn=lambda data: data.real_data.today_energy_kwh,
    ),
    HoymilesPlantSensorDescription(
        key="month_energy",
        name="Month Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:calendar-month",
        value_fn=lambda data: data.real_data.month_energy_kwh,
    ),
    HoymilesPlantSensorDescription(
        key="total_energy",
        name="Lifetime Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:chart-histogram",
        value_fn=lambda data: data.real_data.total_energy_kwh,
    ),
    HoymilesPlantSensorDescription(
        key="co2_reduction",
        name="CO2 Saved",
        native_unit_of_measurement="kg",
        icon="mdi:molecule-co2",
        value_fn=lambda data: data.real_data.co2_reduction_kg,
    ),
    HoymilesPlantSensorDescription(
        key="tree_planted",
        name="Trees Saved",
        native_unit_of_measurement="trees",
        icon="mdi:tree",
        value_fn=lambda data: data.real_data.tree_planted,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hoymiles sensor entities based on a config entry."""
    coordinator: HoymilesDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    # 1. Add plant-level sensors
    for description in PLANT_SENSOR_DESCRIPTIONS:
        entities.append(HoymilesPlantSensor(coordinator, description))

    # 2. Add micro-inverter diagnostic sensors
    for micro_id, micro_state in coordinator.data.micro_inverters.items():
        entities.append(HoymilesMicroAlarmCodeSensor(coordinator, micro_id))
        entities.append(HoymilesMicroAlarmMsgSensor(coordinator, micro_id))

    async_add_entities(entities)


class HoymilesPlantSensor(CoordinatorEntity[HoymilesDataUpdateCoordinator], SensorEntity):
    """Sensor representing plant-wide solar generation metrics."""

    entity_description: HoymilesPlantSensorDescription

    def __init__(
        self,
        coordinator: HoymilesDataUpdateCoordinator,
        description: HoymilesPlantSensorDescription,
    ) -> None:
        """Initialize the plant sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{coordinator.plant_id}_{description.key}"
        self._attr_has_entity_name = True

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the solar plant."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"plant_{self.coordinator.plant_id}")},
            name=self.coordinator.plant_name,
            manufacturer="Hoymiles",
            model="Solar Plant",
            configuration_url="https://global.hoymiles.com/",
        )


class HoymilesMicroAlarmCodeSensor(CoordinatorEntity[HoymilesDataUpdateCoordinator], SensorEntity):
    """Diagnostic sensor for micro-inverter alarm codes."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "alarm_code"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self,
        coordinator: HoymilesDataUpdateCoordinator,
        micro_id: int,
    ) -> None:
        """Initialize the micro alarm code sensor."""
        super().__init__(coordinator)
        self.micro_id = micro_id
        self._attr_unique_id = f"{DOMAIN}_micro_{micro_id}_alarm_code"
        self._attr_name = "Alarm Code"

    @property
    def micro_state(self) -> MicroInverterState | None:
        """Get current micro inverter state."""
        return self.coordinator.data.micro_inverters.get(self.micro_id)

    @property
    def native_value(self) -> int:
        """Return the active alarm code."""
        if self.micro_state:
            return self.micro_state.alarm_code
        return 0

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the micro-inverter."""
        micro = (
            self.micro_state.info
            if self.micro_state
            else None
        )
        sn = micro.sn if micro else str(self.micro_id)
        model = micro.model if micro and micro.model else "Micro Inverter"
        sw = micro.firmware_version if micro else None

        return DeviceInfo(
            identifiers={(DOMAIN, f"micro_{sn}")},
            name=f"Inverter {sn}",
            manufacturer="Hoymiles",
            model=model,
            sw_version=sw,
            via_device=(DOMAIN, f"plant_{self.coordinator.plant_id}"),
        )


class HoymilesMicroAlarmMsgSensor(CoordinatorEntity[HoymilesDataUpdateCoordinator], SensorEntity):
    """Diagnostic sensor for micro-inverter alarm messages."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "alarm_message"
    _attr_icon = "mdi:text-box-search-outline"

    def __init__(
        self,
        coordinator: HoymilesDataUpdateCoordinator,
        micro_id: int,
    ) -> None:
        """Initialize the micro alarm message sensor."""
        super().__init__(coordinator)
        self.micro_id = micro_id
        self._attr_unique_id = f"{DOMAIN}_micro_{micro_id}_alarm_message"
        self._attr_name = "Alarm Message"

    @property
    def micro_state(self) -> MicroInverterState | None:
        """Get current micro inverter state."""
        return self.coordinator.data.micro_inverters.get(self.micro_id)

    @property
    def native_value(self) -> str:
        """Return the human-readable alarm message."""
        if self.micro_state and self.micro_state.alarm_message:
            return self.micro_state.alarm_message
        return "Normal"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the micro-inverter."""
        micro = (
            self.micro_state.info
            if self.micro_state
            else None
        )
        sn = micro.sn if micro else str(self.micro_id)
        model = micro.model if micro and micro.model else "Micro Inverter"
        sw = micro.firmware_version if micro else None

        return DeviceInfo(
            identifiers={(DOMAIN, f"micro_{sn}")},
            name=f"Inverter {sn}",
            manufacturer="Hoymiles",
            model=model,
            sw_version=sw,
            via_device=(DOMAIN, f"plant_{self.coordinator.plant_id}"),
        )
