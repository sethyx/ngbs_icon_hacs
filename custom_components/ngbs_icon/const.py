"""Constants for the NGBS iCON integration."""

from homeassistant.const import Platform

DOMAIN = "ngbs_icon"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
]

# Config entry data keys
CONF_INVENTORY = "inventory"

# Config flow form field for a manually supplied System ID, used as a
# fallback when JSON auto-discovery fails or is skipped entirely.
CONF_SYSID = "sysid"

DEFAULT_SCAN_INTERVAL = 60
DEFAULT_MODBUS_PORT = 502
MIN_SCAN_INTERVAL = 30

MANUFACTURER = "NGBS"
