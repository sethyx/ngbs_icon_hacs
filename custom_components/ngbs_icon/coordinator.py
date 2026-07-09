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

    async def async_refresh_now(self) -> None:
        """Immediately re-read the full dataset and push it to entities.

        Used right after a write so entities reflect the change without
        waiting for the coordinator's normal refresh path, which can be
        debounced. A write to one thermostat can affect thermostats or
        relays on *other* icon controllers too - e.g. the H/C-master
        thermostat's preset can cascade to every zone, and a relay/valve can
        be wired to a different iCON than the thermostat driving it - so this
        always re-reads every controller rather than just the one written to.
        A full read is fast in practice (well under a second). Best effort:
        on failure this silently defers to the next scheduled poll.
        """
        try:
            data = await self.client.async_get_data(self.inventory)
        except IconModbusError as err:
            _LOGGER.debug("Quick refresh failed: %s", err)
            return
        self.async_set_updated_data(data)
