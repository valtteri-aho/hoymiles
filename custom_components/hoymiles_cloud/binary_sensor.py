"""Binary sensor platform for Hoymiles Solar Cloud integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    HoymilesDataUpdateCoordinator,
    MicroInverterState,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hoymiles binary sensor entities based on a config entry."""
    coordinator: HoymilesDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []

    # 1. Plant producing binary sensor
    entities.append(HoymilesPlantProducingBinarySensor(coordinator))

    # 2. Micro-inverter binary sensors (connectivity & problem)
    for micro_id in coordinator.data.micro_inverters:
        entities.append(HoymilesMicroConnectedBinarySensor(coordinator, micro_id))
        entities.append(HoymilesMicroProblemBinarySensor(coordinator, micro_id))

    async_add_entities(entities)


class HoymilesPlantProducingBinarySensor(
    CoordinatorEntity[HoymilesDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor indicating if the plant is actively producing solar power."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_has_entity_name = True
    _attr_name = "Solar Generating"

    def __init__(self, coordinator: HoymilesDataUpdateCoordinator) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.plant_id}_is_generating"

    @property
    def is_on(self) -> bool:
        """Return True if solar generation is above 0 watts."""
        return self.coordinator.data.real_data.real_power_w > 0.0

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


class HoymilesMicroConnectedBinarySensor(
    CoordinatorEntity[HoymilesDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor indicating if a micro-inverter is online/connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Cloud Connectivity"

    def __init__(
        self,
        coordinator: HoymilesDataUpdateCoordinator,
        micro_id: int,
    ) -> None:
        """Initialize the micro-inverter connectivity sensor."""
        super().__init__(coordinator)
        self.micro_id = micro_id
        self._attr_unique_id = f"{DOMAIN}_micro_{micro_id}_connectivity"

    @property
    def micro_state(self) -> MicroInverterState | None:
        """Get current micro inverter state."""
        return self.coordinator.data.micro_inverters.get(self.micro_id)

    @property
    def is_on(self) -> bool:
        """Return True if inverter is connected."""
        if self.micro_state:
            return self.micro_state.connected
        return False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the micro-inverter."""
        micro = self.micro_state.info if self.micro_state else None
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


class HoymilesMicroProblemBinarySensor(
    CoordinatorEntity[HoymilesDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor indicating if a micro-inverter has active alarms."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Problem"

    def __init__(
        self,
        coordinator: HoymilesDataUpdateCoordinator,
        micro_id: int,
    ) -> None:
        """Initialize the micro-inverter problem sensor."""
        super().__init__(coordinator)
        self.micro_id = micro_id
        self._attr_unique_id = f"{DOMAIN}_micro_{micro_id}_problem"

    @property
    def micro_state(self) -> MicroInverterState | None:
        """Get current micro inverter state."""
        return self.coordinator.data.micro_inverters.get(self.micro_id)

    @property
    def is_on(self) -> bool:
        """Return True if inverter has an active alarm or warning."""
        if self.micro_state:
            return bool(
                self.micro_state.alarm_code != 0
                or self.micro_state.info.has_warning
            )
        return False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the micro-inverter."""
        micro = self.micro_state.info if self.micro_state else None
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

