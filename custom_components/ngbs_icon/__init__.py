"""The NGBS iCON integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import IconConfigEntry, IconDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: IconConfigEntry) -> bool:
    """Set up NGBS iCON from a config entry."""
    coordinator = IconDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IconConfigEntry) -> bool:
    """Unload a config entry and close the Modbus connection."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: IconConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
