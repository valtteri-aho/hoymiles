"""Constants for the Hoymiles Solar Cloud integration."""

from __future__ import annotations

from typing import Final
from homeassistant.const import Platform

DOMAIN: Final = "hoymiles_cloud"

# Platforms
PLATFORMS: Final = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Configuration keys
CONF_PLANT_ID: Final = "plant_id"
CONF_PLANT_NAME: Final = "plant_name"
CONF_BASE_URL: Final = "base_url"
CONF_USE_ESTAR: Final = "use_estar"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# Defaults
DEFAULT_SCAN_INTERVAL: Final = 480  # 8 minutes (safe for Hoymiles cloud rate limits)
MIN_SCAN_INTERVAL: Final = 180     # 3 minutes
DEFAULT_BASE_URL: Final = "https://neapi.hoymiles.com/"
ESTAR_BASE_URL: Final = "https://monitor.estarpower.com/platform/api/gateway/"
