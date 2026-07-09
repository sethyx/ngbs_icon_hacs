"""Config flow for the NGBS iCON integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ID, CONF_IP_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .const import (
    CONF_INVENTORY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import IconConfigEntry
from .modbus_client import IconModbusClient, IconModbusError
from .names import IconJsonClient, IconJsonConnectionError, IconJsonError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Required(CONF_ID): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
        ),
    }
)


async def _validate(host: str, sysid: str) -> dict[str, Any]:
    """Validate connectivity and return the naming inventory.

    Fetches names over the legacy JSON protocol (also validates the SYSID) and
    confirms the controller is reachable and discoverable over Modbus.
    """
    inventory = await IconJsonClient(host, sysid).async_fetch_inventory()
    modbus = IconModbusClient(host)
    try:
        await modbus.async_connect()
        present = await modbus.async_discover()
    finally:
        await modbus.async_close()
    if not present:
        raise IconModbusError("No iCON devices discovered over Modbus")
    return inventory


class NgbsIconConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the NGBS iCON config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ID])
            self._abort_if_unique_id_configured()
            try:
                inventory = await _validate(
                    user_input[CONF_IP_ADDRESS], user_input[CONF_ID]
                )
            except (IconJsonConnectionError, IconModbusError):
                errors["base"] = "cannot_connect"
            except IconJsonError:
                errors["base"] = "invalid_id"
            else:
                return self.async_create_entry(
                    title="NGBS iCON",
                    data={**user_input, CONF_INVENTORY: inventory},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ID])
            self._abort_if_unique_id_mismatch()
            try:
                inventory = await _validate(
                    user_input[CONF_IP_ADDRESS], user_input[CONF_ID]
                )
            except (IconJsonConnectionError, IconModbusError):
                errors["base"] = "cannot_connect"
            except IconJsonError:
                errors["base"] = "invalid_id"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={**user_input, CONF_INVENTORY: inventory},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, self._get_reconfigure_entry().data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: IconConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return NgbsIconOptionsFlow(config_entry)


class NgbsIconOptionsFlow(OptionsFlow):
    """Handle NGBS iCON options (poll interval)."""

    def __init__(self, config_entry: IconConfigEntry) -> None:
        """Store the config entry being configured."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll interval option."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
