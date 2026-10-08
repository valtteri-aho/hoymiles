"""Asynchronous Hoymiles S-Miles Cloud API client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp

try:
    from argon2.low_level import Type, hash_secret_raw

    ARGON2_AVAILABLE = True
except ImportError:
    Type = None
    hash_secret_raw = None
    ARGON2_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)

# Base URLs
DEFAULT_BASE_URL = "https://neapi.hoymiles.com/"
ESTAR_BASE_URL = "https://monitor.estarpower.com/platform/api/gateway/"

# Endpoints
ARGON_PRE_INSP_API = "iam/pub/3/auth/pre-insp"
ARGON_LOGIN_API = "iam/pub/3/auth/login"
LEGACY_LOGIN_API = "iam/pub/0/auth/login"

ENDPOINT_STATION_FIND = {
    "0": "pvm/api/0/station/find",
    "1": "pvm/api/0/station/find",
}

ENDPOINT_REAL_DATA = {
    "0": "pvm-data/api/0/station/data/count_station_real_data",
    "1": "pms/v1/station/data/count",
}

ENDPOINT_DEVICE_TREE = {
    "0": "pvm/api/0/station/select_device_of_tree",
    "1": "pms/v1/station/device/tree",
}

ENDPOINT_MICRO_DETAILS = {
    "0": "pvm/api/0/dev/micro/find",
    "1": "pms/v1/device/micro/find",
}

HEADER_JSON = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}


class HoymilesError(Exception):
    """Base exception for Hoymiles Cloud API."""


class HoymilesAuthError(HoymilesError):
    """Authentication or authorization failure."""


class HoymilesConnectionError(HoymilesError):
    """Connection error communicating with Hoymiles API."""


class HoymilesApiError(HoymilesError):
    """API responded with an unexpected error payload."""


@dataclass
class StationSummary:
    """Summary information for a Hoymiles solar station/plant."""

    id: int
    name: str
    capacity: float = 0.0
    status: int = 0
    timezone: str = ""
    address: str = ""


@dataclass
class StationRealData:
    """Real-time data for a solar station."""

    station_id: int
    real_power_w: float = 0.0
    today_energy_kwh: float = 0.0
    month_energy_kwh: float = 0.0
    total_energy_kwh: float = 0.0
    co2_reduction_kg: float = 0.0
    tree_planted: float = 0.0
    data_time: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MicroInverterInfo:
    """Information and real-time state for a micro-inverter."""

    id: int
    sn: str
    model: str = ""
    firmware_version: str = ""
    connected: bool = True
    has_warning: bool = False
    alarm_code: int = 0
    alarm_message: str = ""
    ports: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PlantDevices:
    """Devices registered to a plant."""

    station_id: int
    micro_inverters: list[MicroInverterInfo] = field(default_factory=list)
    raw_tree: list[dict[str, Any]] = field(default_factory=list)


class HoymilesCloudClient:
    """Async client communicating with the Hoymiles S-Miles Cloud API."""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        base_url: str = DEFAULT_BASE_URL,
        use_estar: bool = False,
    ) -> None:
        """Initialize the client."""
        self.username = username
        self.password = password
        self._custom_session = session
        self._session: aiohttp.ClientSession | None = session
        self.base_url = ESTAR_BASE_URL if use_estar else base_url
        self.estar_mode = use_estar
        self.token: str | None = None
        self.api_version: str = "1"
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Ensure an open aiohttp ClientSession."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the underlying session if managed internally."""
        if self._custom_session is None and self._session and not self._session.closed:
            await self._session.close()

    async def _async_argon_compute_challenge(self, salt_hex: str) -> str:
        """Compute the Argon2 ID challenge hash offloaded from event loop."""
        if not ARGON2_AVAILABLE or hash_secret_raw is None or Type is None:
            raise RuntimeError("argon2-cffi is required for modern Hoymiles authentication")

        def _compute() -> str:
            salt = bytes.fromhex(salt_hex)
            raw = hash_secret_raw(
                secret=self.password.encode("utf-8"),
                salt=salt,
                time_cost=3,
                memory_cost=32768,
                parallelism=1,
                hash_len=32,
                type=Type.ID,
            )
            return raw.hex()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _compute)

    async def _request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        requires_auth: bool = True,
        retry_on_auth_fail: bool = True,
    ) -> dict[str, Any]:
        """Send a POST request to the API."""
        url = self.base_url.rstrip("/") + "/" + endpoint.lstrip("/")
        session = await self._get_session()

        headers = dict(HEADER_JSON)
        if requires_auth:
            if not self.token:
                await self.async_login()
            headers["Authorization"] = self.token or ""

        try:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                if response.status in (401, 403):
                    if retry_on_auth_fail:
                        _LOGGER.debug("Got %s, re-authenticating and retrying", response.status)
                        await self.async_login()
                        return await self._request(
                            endpoint, payload, requires_auth, retry_on_auth_fail=False
                        )
                    raise HoymilesAuthError(f"HTTP Authentication failure: {response.status}")

                if response.status != 200:
                    raise HoymilesConnectionError(
                        f"Unexpected HTTP status {response.status} from {endpoint}"
                    )

                data: dict[str, Any] = await response.json()

        except asyncio.TimeoutError as err:
            raise HoymilesConnectionError(f"Timeout connecting to {url}") from err
        except aiohttp.ClientError as err:
            raise HoymilesConnectionError(f"Network error connecting to {url}: {err}") from err

        # Check API status code
        status = str(data.get("status", ""))

        # Status 100 indicates expired token
        if status == "100" and retry_on_auth_fail:
            _LOGGER.debug("API reports token expired (status 100); renewing token")
            await self.async_login()
            return await self._request(
                endpoint, payload, requires_auth, retry_on_auth_fail=False
            )

        if status not in ("0", "200"):
            msg = data.get("message") or f"API error status {status}"
            raise HoymilesApiError(msg)

        return data

    async def async_login(self) -> str:
        """Authenticate with the cloud and acquire an authorization token."""
        async with self._lock:
            # 1. Try modern Argon2 flow first
            if ARGON2_AVAILABLE:
                try:
                    token = await self._async_argon_login()
                    if token:
                        self.token = token
                        self.api_version = "1"
                        _LOGGER.debug("Logged in successfully using Argon2 (API v1)")
                        return token
                except Exception as err:
                    _LOGGER.debug("Argon2 authentication failed, falling back to legacy: %s", err)

            # 2. Fallback to legacy MD5 flow
            token = await self._async_legacy_login()
            if token:
                self.token = token
                self.api_version = "0"
                _LOGGER.debug("Logged in successfully using legacy MD5 (API v0)")
                return token

            raise HoymilesAuthError("Failed to authenticate with Hoymiles Cloud API")

    async def _async_argon_login(self) -> str | None:
        """Execute Argon2 pre-inspect and challenge-response authentication."""
        url = self.base_url.rstrip("/") + "/" + ARGON_PRE_INSP_API
        session = await self._get_session()

        pre_insp_payload = {"u": self.username}
        async with session.post(
            url, json=pre_insp_payload, headers=HEADER_JSON, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        if str(data.get("status")) != "0":
            return None

        insp_data = data.get("data", {})
        nonce = insp_data.get("n")
        salt = insp_data.get("a")
        if not nonce or not salt:
            return None

        challenge = await self._async_argon_compute_challenge(salt)

        login_url = self.base_url.rstrip("/") + "/" + ARGON_LOGIN_API
        login_payload = {"u": self.username, "ch": challenge, "n": nonce}
        async with session.post(
            login_url, json=login_payload, headers=HEADER_JSON, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return None
            login_data = await resp.json()

        if str(login_data.get("status")) != "0":
            return None

        return login_data.get("data", {}).get("token")

    async def _async_legacy_login(self) -> str | None:
        """Execute legacy MD5 authentication."""
        pass_hash = hashlib.md5(self.password.encode("utf-8")).hexdigest()
        url = self.base_url.rstrip("/") + "/" + LEGACY_LOGIN_API
        session = await self._get_session()

        payload = {
            "password": pass_hash,
            "user_name": self.username,
        }
        async with session.post(
            url, json=payload, headers=HEADER_JSON, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        if str(data.get("status")) != "0":
            return None

        token_data = data.get("data", {})
        return token_data.get("token") or token_data.get("estar_token")

    async def async_get_stations(self) -> list[StationSummary]:
        """Fetch list of solar stations accessible by the account."""
        endpoint = ENDPOINT_STATION_FIND.get(self.api_version, ENDPOINT_STATION_FIND["0"])
        # Some accounts use {"id": ""} or empty payload
        response = await self._request(endpoint, {})
        data = response.get("data", {})

        stations: list[StationSummary] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("list", [data]) if "list" in data else [data]
        else:
            items = []

        for item in items:
            if not isinstance(item, dict) or "id" not in item:
                continue
            stations.append(
                StationSummary(
                    id=int(item["id"]),
                    name=item.get("station_name") or item.get("name") or f"Plant {item['id']}",
                    capacity=float(item.get("capacity") or item.get("capacitor") or 0.0),
                    status=int(item.get("status", 0)),
                    timezone=str(item.get("timezone") or item.get("tz_name") or ""),
                    address=str(item.get("address") or item.get("location") or ""),
                )
            )

        return stations

    async def async_get_real_data(self, station_id: int) -> StationRealData:
        """Fetch real-time metrics for a station."""
        endpoint = ENDPOINT_REAL_DATA.get(self.api_version, ENDPOINT_REAL_DATA["0"])
        payload = (
            {"station_id": int(station_id)}
            if self.api_version == "1"
            else {"sid": str(station_id)}
        )

        response = await self._request(endpoint, payload)
        data = response.get("data", {})

        real_power = float(data.get("real_power") or 0.0)
        today_eq = float(data.get("today_eq") or 0.0)
        month_eq = float(data.get("month_eq") or 0.0)
        total_eq = float(data.get("total_eq") or 0.0)
        co2 = float(data.get("co2_emission_reduction") or data.get("co2_emission") or 0.0)
        tree = float(data.get("plant_tree") or data.get("tree_planted") or 0.0)
        data_time = str(data.get("data_time") or data.get("last_data_time") or "")

        return StationRealData(
            station_id=int(station_id),
            real_power_w=real_power,
            today_energy_kwh=today_eq,
            month_energy_kwh=month_eq,
            total_energy_kwh=total_eq,
            co2_reduction_kg=co2,
            tree_planted=tree,
            data_time=data_time,
            raw=data,
        )

    async def async_get_devices(self, station_id: int) -> PlantDevices:
        """Fetch hardware and micro-inverter device tree for a station."""
        endpoint = ENDPOINT_DEVICE_TREE.get(self.api_version, ENDPOINT_DEVICE_TREE["0"])
        payload = (
            {"station_id": int(station_id)}
            if self.api_version == "1"
            else {"id": str(station_id)}
        )

        response = await self._request(endpoint, payload)
        raw_tree = response.get("data", [])

        micro_inverters: list[MicroInverterInfo] = []
        self._parse_device_tree_items(raw_tree, micro_inverters)

        return PlantDevices(
            station_id=int(station_id),
            micro_inverters=micro_inverters,
            raw_tree=raw_tree,
        )

    def _parse_device_tree_items(
        self, items: list[dict[str, Any]], out_micros: list[MicroInverterInfo]
    ) -> None:
        """Recursively extract micro-inverters from the device hierarchy."""
        for item in items:
            if not isinstance(item, dict):
                continue

            # dev_type: 3 = micro-inverter, 6 = hybrid inverter
            dev_type = item.get("type")
            item_text = str(item.get("text", "")).lower()
            if dev_type in (3, 6) or any(k in item_text for k in ("micro", "inverter")):
                micro_id = item.get("id")
                sn = str(item.get("sn") or micro_id)
                model = str(item.get("model_no") or "")
                soft_ver = str(item.get("soft_ver") or "")
                warn_data = item.get("warn_data") or {}

                connected = True
                has_warn = False
                if isinstance(warn_data, dict):
                    connected = warn_data.get("connect", True)
                    has_warn = warn_data.get("warn", False)

                out_micros.append(
                    MicroInverterInfo(
                        id=int(micro_id),
                        sn=sn,
                        model=model,
                        firmware_version=soft_ver,
                        connected=connected,
                        has_warning=has_warn,
                    )
                )

            # Recurse through children
            children = item.get("children", [])
            if isinstance(children, list) and children:
                self._parse_device_tree_items(children, out_micros)

    async def async_get_micro_details(
        self, micro_id: int, station_id: int
    ) -> tuple[bool, int, str]:
        """Fetch real-time connectivity and alarms for a micro-inverter.

        Returns (connected, alarm_code, alarm_message).
        """
        endpoint = ENDPOINT_MICRO_DETAILS.get(
            self.api_version, ENDPOINT_MICRO_DETAILS["0"]
        )
        payload = (
            {"station_id": int(station_id)}
            if self.api_version == "1"
            else {"id": str(micro_id)}
        )

        response = await self._request(endpoint, payload)
        data = response.get("data", {})

        connected = bool(data.get("net_state", 1))
        warn_list = data.get("warn_list", [])

        alarm_code = 0
        alarm_message = ""
        if isinstance(warn_list, list) and warn_list:
            first_warn = warn_list[0]
            if isinstance(first_warn, dict):
                alarm_code = int(first_warn.get("err_code", 0))
                parts = [
                    first_warn.get("wd1", "").strip(),
                    first_warn.get("wdd1", "").strip(),
                    first_warn.get("wdd2", "").strip(),
                    first_warn.get("wd2", "").strip(),
                ]
                alarm_message = " ".join([p for p in parts if p and p != "-"])

        return connected, alarm_code, alarm_message

