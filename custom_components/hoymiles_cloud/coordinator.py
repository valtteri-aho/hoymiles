"""DataUpdateCoordinator for Hoymiles Solar Cloud integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    HoymilesAuthError,
    HoymilesCloudClient,
    HoymilesConnectionError,
    HoymilesError,
    MicroInverterInfo,
    PlantDevices,
    StationRealData,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class MicroInverterState:
    """Consolidated state for a single micro-inverter."""

    info: MicroInverterInfo
    connected: bool = True
    alarm_code: int = 0
    alarm_message: str = ""


@dataclass
class HoymilesCoordinatorData:
    """Aggregated data payload returned by the coordinator."""

    plant_id: int
    plant_name: str
    real_data: StationRealData
    micro_inverters: dict[int, MicroInverterState] = field(default_factory=dict)
    raw_devices: list[dict[str, Any]] = field(default_factory=list)


class HoymilesDataUpdateCoordinator(DataUpdateCoordinator[HoymilesCoordinatorData]):
    """Manage fetching Hoymiles cloud data for a single solar plant."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HoymilesCloudClient,
        plant_id: int,
        plant_name: str,
        update_interval_seconds: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{plant_id}",
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.client = client
        self.plant_id = plant_id
        self.plant_name = plant_name
        self._cached_devices: PlantDevices | None = None

    async def _async_update_data(self) -> HoymilesCoordinatorData:
        """Fetch fresh metrics from Hoymiles cloud."""
        try:
            # 1. Fetch real-time solar generation metrics
            real_data = await self.client.async_get_real_data(self.plant_id)

            # 2. Fetch or reuse device tree structure
            if self._cached_devices is None:
                self._cached_devices = await self.client.async_get_devices(self.plant_id)

            # 3. Fetch real-time diagnostics and alarm status for each micro-inverter
            micro_states: dict[int, MicroInverterState] = {}
            for micro in self._cached_devices.micro_inverters:
                try:
                    conn, code, msg = await self.client.async_get_micro_details(
                        micro_id=micro.id, station_id=self.plant_id
                    )
                    micro_states[micro.id] = MicroInverterState(
                        info=micro,
                        connected=conn,
                        alarm_code=code,
                        alarm_message=msg,
                    )
                except HoymilesError as err:
                    _LOGGER.debug(
                        "Failed fetching details for micro %s: %s; using fallback",
                        micro.id,
                        err,
                    )
                    micro_states[micro.id] = MicroInverterState(
                        info=micro,
                        connected=micro.connected,
                        alarm_code=0,
                        alarm_message="",
                    )

            return HoymilesCoordinatorData(
                plant_id=self.plant_id,
                plant_name=self.plant_name,
                real_data=real_data,
                micro_inverters=micro_states,
                raw_devices=self._cached_devices.raw_tree,
            )

        except HoymilesAuthError as err:
            raise UpdateFailed(f"Authentication failure: {err}") from err
        except HoymilesConnectionError as err:
            raise UpdateFailed(f"Connection failure communicating with cloud: {err}") from err
        except HoymilesError as err:
            raise UpdateFailed(f"Hoymiles API error: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching Hoymiles data")
            raise UpdateFailed(f"Unexpected error: {err}") from err

