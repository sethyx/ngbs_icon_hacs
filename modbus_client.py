"""Modbus-TCP client library for NGBS iCON controllers.

This module is intentionally free of any Home Assistant imports so it can be
reused by the integration and by the standalone CLI tools in ``tools/``.

A single :class:`AsyncModbusTcpClient` connection is opened once and kept alive
for the lifetime of the client; reads/writes reconnect transparently if the
socket drops. Data is decoded into the shared *canonical schema* documented in
``async_get_data``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

try:  # package import (Home Assistant) vs. standalone import (CLI tools)
    from . import modbus_registers as reg
except ImportError:  # pragma: no cover - standalone script fallback
    import modbus_registers as reg

_LOGGER = logging.getLogger(__name__)


class IconModbusError(Exception):
    """Base exception for the iCON Modbus client."""


class IconModbusConnectionError(IconModbusError):
    """Raised when the controller cannot be reached."""


def _signed(value: int) -> int:
    """Interpret a 16-bit register as a signed two's-complement integer."""
    return value - 0x10000 if value >= 0x8000 else value


def _temp(raw: int | None) -> float | None:
    """Decode an x0.1 signed temperature register, honouring the fault value."""
    if raw is None or raw == reg.SENSOR_FAULT:
        return None
    return round(_signed(raw) * 0.1, 1)


def _rh(raw: int | None) -> float | None:
    """Decode an x0.1 relative-humidity register."""
    if raw is None:
        return None
    return round(raw * 0.1, 1)


def _bit(word: int, index: int) -> bool:
    """Return bit ``index`` of ``word`` as a bool."""
    return bool((word >> index) & 1)


class IconModbusClient:
    """Persistent Modbus-TCP client for an NGBS iCON bus."""

    def __init__(
        self, host: str, port: int = 502, unit: int = 0, timeout: float = 5.0
    ) -> None:
        """Initialise the client. The connection is opened by ``async_connect``."""
        self._host = host
        self._port = port
        self._unit = unit
        self._timeout = timeout
        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()

    # -- connection management ------------------------------------------------

    async def async_connect(self) -> None:
        """Open the persistent connection (idempotent)."""
        if self._client is None:
            self._client = AsyncModbusTcpClient(
                self._host, port=self._port, timeout=self._timeout
            )
        if not self._client.connected:
            _LOGGER.debug("Connecting to iCON Modbus at %s:%s", self._host, self._port)
            connected = await self._client.connect()
            if not connected:
                raise IconModbusConnectionError(
                    f"Could not connect to {self._host}:{self._port}"
                )

    async def async_close(self) -> None:
        """Close the persistent connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    async def _ensure_connected(self) -> AsyncModbusTcpClient:
        """Return a connected client, reconnecting if the socket dropped."""
        await self.async_connect()
        assert self._client is not None
        return self._client

    # -- low-level reads ------------------------------------------------------

    async def _read_block(self, device_index: int) -> list[int] | None:
        """Read the full standard block of a device, or None if unreachable."""
        address = reg.device_base(device_index) + reg.READ_START
        client = await self._ensure_connected()
        try:
            result = await client.read_holding_registers(
                address, count=reg.READ_COUNT, slave=self._unit
            )
        except ModbusException as err:
            # Drop the connection so the next call reconnects cleanly.
            await self.async_close()
            raise IconModbusConnectionError(f"Modbus read failed: {err}") from err
        if result.isError():
            return None
        return list(result.registers)

    # -- discovery ------------------------------------------------------------

    async def async_discover(self) -> list[int]:
        """Return the indices of devices that are present on the bus.

        A device is considered present when its firmware-version register
        (``PrgVer``) reads back non-zero.
        """
        present: list[int] = []
        async with self._lock:
            for device_index in range(reg.MAX_DEVICES):
                block = await self._read_block(device_index)
                if block is not None and block[reg.OFF_PRGVER] != 0:
                    present.append(device_index)
        return present

    # -- full data fetch ------------------------------------------------------

    async def async_get_data(
        self, inventory: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Fetch and decode the full dataset into the canonical schema.

        Canonical schema::

            {
              "system": {"cooling": bool, "water_temp": float|None,
                         "outdoor_temp": float|None},
              "icons": {
                "<icon_num>": {
                  "mixing_valve_pct": float|None,
                  "thermostats": {"<icon_num>.<th>": {...}},
                  "relays": {"R<n>": {"name": str|None, "on": bool}},
                }
              }
            }

        ``inventory`` (from the JSON setup path) is optional and only used to
        fill in human-readable thermostat/relay ``name`` fields.
        """
        inventory = inventory or {}
        therm_names: dict[str, str] = inventory.get("thermostats", {})
        relay_names: dict[str, dict[str, str]] = inventory.get("relays", {})

        blocks: dict[int, list[int]] = {}
        async with self._lock:
            for device_index in range(reg.MAX_DEVICES):
                block = await self._read_block(device_index)
                if block is not None and block[reg.OFF_PRGVER] != 0:
                    blocks[device_index] = block

        if not blocks:
            raise IconModbusConnectionError("No iCON devices responded")

        master_index = min(blocks)
        master = blocks[master_index]
        system_cooling = master[reg.OFF_HCMODE] == 1

        data: dict[str, Any] = {
            "system": {
                "cooling": system_cooling,
                "pump": _bit(master[reg.OFF_DI], reg.DI_PUMP_BIT),
                "water_temp": _temp(master[reg.OFF_WATER_TEMP]),
                "outdoor_temp": _temp(master[reg.OFF_TEX]),
            },
            "icons": {},
        }

        for device_index, block in blocks.items():
            icon_num = device_index + 1
            icon_key = str(icon_num)
            icon_relay_names = relay_names.get(icon_key, {})

            demand_mask = block[reg.OFF_REG_A] | block[reg.OFF_REG_B]
            eco_mask = block[reg.OFF_ECO]
            noconn_mask = block[reg.OFF_NOCONN]
            live_mask = block[reg.OFF_LIVE]
            relay_word = block[reg.OFF_RELAY]

            thermostats: dict[str, Any] = {}
            for th in range(1, reg.MAX_THERMOSTATS + 1):
                bit = th - 1
                if not _bit(live_mask, bit) or _bit(noconn_mask, bit):
                    continue
                th_id = f"{icon_num}.{th}"
                sp_base = reg.OFF_SETPOINT + bit * 4
                sp_heat_normal = _temp(block[sp_base + reg.SP_HEAT_NORMAL])
                sp_cool_normal = _temp(block[sp_base + reg.SP_COOL_NORMAL])
                sp_heat_eco = _temp(block[sp_base + reg.SP_HEAT_ECO])
                sp_cool_eco = _temp(block[sp_base + reg.SP_COOL_ECO])
                eco = _bit(eco_mask, bit)
                if eco:
                    target = sp_cool_eco if system_cooling else sp_heat_eco
                else:
                    target = sp_cool_normal if system_cooling else sp_heat_normal

                thermostats[th_id] = {
                    "name": therm_names.get(th_id),
                    "temp": _temp(block[reg.OFF_TEMP + bit]),
                    "rh": _rh(block[reg.OFF_RH + bit]),
                    "dew": _temp(block[reg.OFF_DEW + bit]),
                    "eco": eco,
                    "demand": _bit(demand_mask, bit),
                    "cooling": system_cooling,
                    "target": target,
                    "sp_heat_normal": sp_heat_normal,
                    "sp_cool_normal": sp_cool_normal,
                    "sp_heat_eco": sp_heat_eco,
                    "sp_cool_eco": sp_cool_eco,
                }

            relays: dict[str, Any] = {}
            for relay_id, bit_index in reg.RELAY_BIT_FOR_ID.items():
                key = f"R{relay_id}"
                relays[key] = {
                    "name": icon_relay_names.get(key),
                    "on": _bit(relay_word, bit_index),
                }

            ao = block[reg.OFF_AO]
            data["icons"][icon_key] = {
                "firmware": block[reg.OFF_PRGVER],
                "mixing_valve_pct": round(ao / 10.0, 1),
                "thermostats": thermostats,
                "relays": relays,
            }

        return data

    # -- writes ---------------------------------------------------------------

    @staticmethod
    def _split_id(thermostat_id: str) -> tuple[int, int]:
        """Split an ``"<icon>.<th>"`` id into (device_index, thermostat_num)."""
        icon_str, th_str = thermostat_id.split(".")
        return int(icon_str) - 1, int(th_str)

    async def _write(self, address: int, value: int) -> None:
        client = await self._ensure_connected()
        try:
            result = await client.write_registers(
                address, [value], slave=self._unit
            )
        except ModbusException as err:
            await self.async_close()
            raise IconModbusConnectionError(f"Modbus write failed: {err}") from err
        if result.isError():
            raise IconModbusError(f"Write to 0x{address:04X} rejected")

    async def async_set_temperature(
        self, thermostat_id: str, temperature: float, cooling: bool, eco: bool
    ) -> None:
        """Write the active setpoint for a thermostat.

        The register chosen depends on the current mode (cooling/heating) and
        preset (eco/normal), mirroring the four-setpoint model of the device.
        """
        device_index, th = self._split_id(thermostat_id)
        if cooling:
            slot = reg.SP_COOL_ECO if eco else reg.SP_COOL_NORMAL
        else:
            slot = reg.SP_HEAT_ECO if eco else reg.SP_HEAT_NORMAL
        raw = max(reg.SETPOINT_MIN, min(reg.SETPOINT_MAX, round(temperature * 10)))
        address = reg.device_base(device_index) + reg.OFF_SP_WRITE + (th - 1) * 4 + slot
        async with self._lock:
            await self._write(address, raw)

    async def async_set_hvac_mode(self, cooling: bool) -> None:
        """Switch the whole system between heating and cooling (master only)."""
        address = reg.device_base(0) + reg.OFF_MASTER_HC
        async with self._lock:
            await self._write(address, 1 if cooling else 0)

    async def async_set_preset_mode(self, thermostat_id: str, eco: bool) -> None:
        """Set ECO (True) or normal (False) preset for a thermostat."""
        device_index, th = self._split_id(thermostat_id)
        address = reg.device_base(device_index) + reg.OFF_ECO_CMD + (th - 1)
        async with self._lock:
            await self._write(address, 1 if eco else 0)
