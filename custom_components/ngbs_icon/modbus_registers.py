"""Modbus register map for NGBS iCON controllers.

All offsets are relative to a per-device base address unless documented as
absolute. See ``iCON_MODBUS_Register_Map.md`` for the full specification.

Temperature / humidity registers use x0.1 scaling (215 -> 21.5).
Negative temperatures use two's complement. Temperature sensor faults read
back as ``SENSOR_FAULT`` (2220).
"""

from __future__ import annotations

# --- Device layout ----------------------------------------------------------

MAX_DEVICES = 8  # 1 master + up to 7 slaves
MAX_THERMOSTATS = 8  # per device


def device_base(device_index: int) -> int:
    """Return the standard-block base address for a device index (0..7)."""
    return 0x0100 * (device_index + 1)


# --- Standard block offsets (relative to device_base) -----------------------

# Status bit registers (bit 0..7 -> thermostat 1..8)
OFF_REG_A = 0x0000  # A-loop output, bit=1 energy demand
OFF_REG_B = 0x0001  # B-loop output, bit=1 energy demand
OFF_ECO = 0x0004  # ECO mode, bit=1 ECO
OFF_HC = 0x0006  # Heating/Cooling state, bit=1 cooling
OFF_NOCONN = 0x0008  # No thermostat connection / not configured, bit=1
OFF_RELAY = 0x000A  # Relay regulation state bitfield
OFF_DI = 0x000B  # Digital inputs / system bits
OFF_LIVE = 0x000E  # Thermostat connection alive, bit=1

DI_PUMP_BIT = 8  # Di register: pump active (any A or B loop)

# Analog registers
OFF_AO = 0x0010  # Mixing valve output, 0..1000 = 0..10V
OFF_WATER_TEMP = 0x0011  # Ai.0 water temperature, x0.1 C
OFF_OUTDOOR_TEMP = 0x0012  # Ai.1 outdoor temperature, x0.1 C

# Per-thermostat measurements (index 0..7 -> thermostat 1..8)
OFF_TEMP = 0x0019  # Temp.1..8, x0.1 C
OFF_RH = 0x0021  # Rh.1..8, x0.1 %RH
OFF_DEW = 0x0029  # Dewp.1..8, x0.1 C

# Active setpoints, 4 per thermostat: heat-normal, cool-normal, heat-eco, cool-eco
OFF_SETPOINT = 0x0031  # x0.1 C; thermostat t (1..8) -> OFF_SETPOINT + (t-1)*4

# System state
OFF_HCMODE = 0x0051  # 0=heat, 1=cool, >1 switchover in progress
OFF_TEX = 0x0052  # effective outdoor temperature, x0.1 C
OFF_PRGVER = 0x0054  # firmware version, 0 on unreachable slave -> used for discovery

# Single read window that covers everything above (offset 0x00..0x57 inclusive)
READ_START = 0x0000
READ_COUNT = 0x0058  # 88 registers, < 125 (FC3 limit)

# --- Write offsets (relative to device_base) --------------------------------

OFF_MASTER_HC = 0x0062  # system H/C switch (master only): 0=heat, 1=cool
OFF_ECO_CMD = 0x0063  # ECO.1..8 command; thermostat t -> OFF_ECO_CMD + (t-1)
OFF_SP_WRITE = 0x0083  # setpoint write, 4 per thermostat, same order as OFF_SETPOINT

# Setpoint slot order within a thermostat's 4-register group.
SP_HEAT_NORMAL = 0
SP_COOL_NORMAL = 1
SP_HEAT_ECO = 2
SP_COOL_ECO = 3

# --- Value semantics --------------------------------------------------------

SENSOR_FAULT = 2220  # raw value indicating a temperature sensor fault
SETPOINT_MIN = 50  # 5.0 C
SETPOINT_MAX = 350  # 35.0 C

# Relay bitfield (register OFF_RELAY) -> JSON relay id "R<n>" mapping.
# The controller packs relay states as: bit0 = heating relay, bit1..8 = valve
# outputs 1..8, bit9 = cooling relay. The legacy JSON protocol exposes the same
# relays as R0..R9. The default hypothesis is a straight R<n> -> bit<n> mapping;
# this is verified/adjusted with tools/compare.py against a live controller.
RELAY_BIT_FOR_ID = {n: n for n in range(10)}
