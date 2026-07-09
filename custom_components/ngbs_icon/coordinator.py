"""Data update coordinator for the NGBS iCON integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_IP_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_INVENTORY,
    DEFAULT_MODBUS_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .modbus_client import IconModbusClient, IconModbusError

_LOGGER = logging.getLogger(__name__)

type IconConfigEntry = ConfigEntry[IconDataUpdateCoordinator]


class IconDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the controller over the persistent Modbus connection."""

    config_entry: IconConfigEntry

    def __init__(self, hass: HomeAssistant, entry: IconConfigEntry) -> None:
        """Initialize the coordinator and the Modbus client."""
        self.sysid: str = entry.data[CONF_ID]
        self.inventory: dict[str, Any] = entry.data.get(CONF_INVENTORY, {})
        self.client = IconModbusClient(
            entry.data[CONF_IP_ADDRESS], port=DEFAULT_MODBUS_PORT
        )
        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the full dataset from the controller."""
        try:
            return await self.client.async_get_data(self.inventory)
        except IconModbusError as err:
            raise UpdateFailed(f"Error communicating with iCON: {err}") from err
