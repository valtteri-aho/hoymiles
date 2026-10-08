"""Config flow for Hoymiles Solar Cloud integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import (
    HoymilesAuthError,
    HoymilesCloudClient,
    HoymilesConnectionError,
    HoymilesError,
    StationSummary,
)
from .const import (
    CONF_BASE_URL,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    CONF_SCAN_INTERVAL,
    CONF_USE_ESTAR,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class HoymilesCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hoymiles Solar Cloud."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._username: str | None = None
        self._password: str | None = None
        self._use_estar: bool = False
        self._stations: list[StationSummary] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            self._password = user_input[CONF_PASSWORD].strip()
            self._use_estar = user_input.get(CONF_USE_ESTAR, False)
            manual_plant_id = user_input.get(CONF_PLANT_ID)

            session = async_get_clientsession(self.hass)
            client = HoymilesCloudClient(
                username=self._username,
                password=self._password,
                session=session,
                use_estar=self._use_estar,
            )

            try:
                await client.async_login()

                if manual_plant_id:
                    plant_id = int(str(manual_plant_id).strip())
                    await self.async_set_unique_id(f"{DOMAIN}_{plant_id}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"Hoymiles Plant {plant_id}",
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                            CONF_PLANT_ID: plant_id,
                            CONF_PLANT_NAME: f"Hoymiles Plant {plant_id}",
                            CONF_USE_ESTAR: self._use_estar,
                            CONF_BASE_URL: client.base_url,
                        },
                    )

                # Auto-discover stations
                self._stations = await client.async_get_stations()
                if not self._stations:
                    errors["base"] = "no_stations_found"
                elif len(self._stations) == 1:
                    station = self._stations[0]
                    await self.async_set_unique_id(f"{DOMAIN}_{station.id}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=station.name,
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                            CONF_PLANT_ID: station.id,
                            CONF_PLANT_NAME: station.name,
                            CONF_USE_ESTAR: self._use_estar,
                            CONF_BASE_URL: client.base_url,
                        },
                    )
                else:
                    return await self.async_step_select_station()

            except HoymilesAuthError:
                errors["base"] = "invalid_auth"
            except HoymilesConnectionError:
                errors["base"] = "cannot_connect"
            except HoymilesError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception in Hoymiles config flow")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_PLANT_ID): str,
                vol.Optional(CONF_USE_ESTAR, default=False): bool,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_select_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle selecting from multiple stations."""
        errors: dict[str, str] = {}

        if user_input is not None:
            plant_id = int(user_input[CONF_PLANT_ID])
            selected = next((s for s in self._stations if s.id == plant_id), None)
            title = selected.name if selected else f"Hoymiles Plant {plant_id}"

            await self.async_set_unique_id(f"{DOMAIN}_{plant_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=title,
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_PLANT_ID: plant_id,
                    CONF_PLANT_NAME: title,
                    CONF_USE_ESTAR: self._use_estar,
                },
            )

        station_options = {s.id: f"{s.name} (ID: {s.id})" for s in self._stations}
        schema = vol.Schema(
            {
                vol.Required(CONF_PLANT_ID): vol.In(station_options),
            }
        )

        return self.async_show_form(
            step_id="select_station", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HoymilesCloudOptionsFlow:
        """Get the options flow for this handler."""
        return HoymilesCloudOptionsFlow(config_entry)


class HoymilesCloudOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Hoymiles Solar Cloud."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current_interval,
                ): vol.All(vol.Coerce(int), vol.Clamp(min=MIN_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
