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
    DEFAULT_MODBUS_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import IconConfigEntry
from .modbus_client import (
    IconModbusClient,
    IconModbusConnectionError,
    IconModbusError,
)
from .names import (
    IconJsonClient,
    IconJsonConnectionError,
    IconJsonError,
    async_discover_sysid,
)

_LOGGER = logging.getLogger(__name__)


class ValidationFailed(Exception):
    """A setup check failed, carrying the error key and a human-readable reason."""

    def __init__(self, error: str, reason: str) -> None:
        """Store the strings.json error key and the detailed reason."""
        super().__init__(reason)
        self.error = error
        self.reason = reason


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
        ),
    }
)


async def _validate(host: str) -> tuple[str, dict[str, Any]]:
    """Discover the SYSID and validate connectivity, returning it with the inventory.

    The SYSID is auto-detected over the legacy JSON protocol (no prior
    knowledge of it needed), then used to fetch the naming inventory. Modbus
    reachability is confirmed separately, and the discovered device indices
    are cached into the inventory so the coordinator doesn't need to re-probe
    every device slot on every poll - only setup/reconfigure does that full
    scan. Re-running Reconfigure after adding or removing a controller
    refreshes this cache.

    Each stage is wrapped so the user sees which one failed and why, instead of
    a bare "cannot connect".
    """
    # Stage 1: reach the controller on the JSON port and auto-detect the SYSID.
    try:
        sysid = await async_discover_sysid(host)
    except IconJsonConnectionError as err:
        raise ValidationFailed("cannot_connect_json", str(err)) from err
    except IconJsonError as err:
        raise ValidationFailed("invalid_json_response", str(err)) from err

    # Stage 2: fetch the naming inventory, which requires the SYSID to be valid.
    try:
        inventory = await IconJsonClient(host, sysid).async_fetch_inventory()
    except IconJsonConnectionError as err:
        raise ValidationFailed("cannot_connect_json", str(err)) from err
    except IconJsonError as err:
        raise ValidationFailed("invalid_inventory", str(err)) from err

    # Stage 3: confirm Modbus-TCP reachability and scan for devices.
    modbus = IconModbusClient(host)
    try:
        await modbus.async_connect()
        present = await modbus.async_discover()
    except IconModbusConnectionError as err:
        raise ValidationFailed("cannot_connect_modbus", str(err)) from err
    except IconModbusError as err:
        raise ValidationFailed("modbus_error", str(err)) from err
    finally:
        await modbus.async_close()

    if not present:
        raise ValidationFailed(
            "no_devices",
            f"Connected to {host}:{DEFAULT_MODBUS_PORT} over Modbus-TCP and the "
            f"JSON port reported SYSID {sysid}, but none of the device slots "
            "returned a firmware version, so no iCON unit could be identified. "
            "Check that the units are powered and addressed on the bus.",
        )
    inventory["device_indices"] = present
    return sysid, inventory


class NgbsIconConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the NGBS iCON config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                sysid, inventory = await _validate(user_input[CONF_IP_ADDRESS])
            except ValidationFailed as err:
                _LOGGER.error("NGBS iCON setup failed: %s", err.reason)
                errors["base"] = err.error
                placeholders["reason"] = err.reason
            except Exception as err:  # noqa: BLE001 - surface the real cause
                _LOGGER.exception("Unexpected error during NGBS iCON setup")
                errors["base"] = "unknown"
                placeholders["reason"] = f"{type(err).__name__}: {err}"
            else:
                await self.async_set_unique_id(sysid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="NGBS iCON",
                    data={**user_input, CONF_ID: sysid, CONF_INVENTORY: inventory},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                sysid, inventory = await _validate(user_input[CONF_IP_ADDRESS])
            except ValidationFailed as err:
                _LOGGER.error("NGBS iCON reconfigure failed: %s", err.reason)
                errors["base"] = err.error
                placeholders["reason"] = err.reason
            except Exception as err:  # noqa: BLE001 - surface the real cause
                _LOGGER.exception("Unexpected error during NGBS iCON reconfigure")
                errors["base"] = "unknown"
                placeholders["reason"] = f"{type(err).__name__}: {err}"
            else:
                await self.async_set_unique_id(sysid)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={
                        **user_input,
                        CONF_ID: sysid,
                        CONF_INVENTORY: inventory,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, self._get_reconfigure_entry().data
            ),
            errors=errors,
            description_placeholders=placeholders,
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
