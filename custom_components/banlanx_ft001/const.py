"""Constants for the BanlanX FT001 integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "banlanx_ft001"
DEFAULT_NAME = "BanlanX FT001"
DEFAULT_PORT = 8587
DEFAULT_SCAN_INTERVAL = 15
FT001_MODEL_CODE = 0x96

CONF_LOCAL_NAME = "local_name"
CONF_MAC_ADDRESS = "mac_address"
CONF_MODEL_CODE = "model_code"
CONF_SCAN_INTERVAL = "scan_interval"

MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300

PLATFORMS = [Platform.LIGHT]
