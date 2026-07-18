# iCON-1 / iCON-2 MODBUS-TCP Register Map

> **Source:** NGBS iCON Modbus V1.15 HU — <https://www.ngbsh.hu>
> **Firmware compatibility:** ≥ 1060
> **Language of original:** Hungarian (translated/structured for machine consumption)

---

## 1. Communication Overview

The iCON-1 controller exposes a **MODBUS-TCP Class-0 Slave** (TCP server) on its Ethernet interface.

| Parameter | Value |
|---|---|
| Transport | TCP, port **502** |
| Interface | Ethernet 10/100 Base-T, RJ-45, CAT-5+ |
| Max cable length | 100 m (to switch) |
| Addressing | IPv4 (DHCP default, static configurable) |
| Unit Number | 0 (default) |
| Max controllers per bus | 8 iCON (1 Master + 7 Slaves via RS485, max 1200 m) |
| Max thermostats per bus | 64 (8 per iCON) |
| Supported function codes | **3** (Read Multiple Registers, max 125/msg), **16** (Write Multiple Registers, max 123/msg) |

### Capabilities via MODBUS-TCP

**Readable:** controller regulation state, I/O states, thermostat measurements (temperature, RH%, dew point), active setpoints, status flags, slave device data.

**Writable:** heating/cooling mode switch, ECO mode per thermostat, individual setpoints (4 per thermostat: heat-normal, cool-normal, heat-ECO, cool-ECO), keypad lock, relay override, alternative outdoor temperature, fan-coil speed, individual H/C switching.

### Notes

- Out-of-range register reads return **0** (no error).
- Out-of-range register writes are **rejected**.
- Negative values (e.g. outdoor temperature) use **two's complement** (0xFFFF = −0.1 °C).
- Modified thermostat parameters are saved to EEPROM after ~3–5 min of no further writes.
- Override states are **not** persisted across power cycles.
- In island mode (no internet), disable network watchdog and use a local NTP server to prevent periodic interface restarts.

---

## 2. Address Space Layout

Each iCON device on the RS485 bus gets its own register block. Register offsets from section 3 must be **added** to the device base address.

### Standard register blocks (per-device, offset-based)

| RTU Address | Role | Base Address (hex) | Base Address (dec) |
|---|---|---|---|
| 1 | **Master iCON-1** | 0x0100 | 256 |
| 2 | Slave 1 | 0x0200 | 512 |
| 3 | Slave 2 | 0x0300 | 768 |
| 4 | Slave 3 | 0x0400 | 1024 |
| 5 | Slave 4 | 0x0500 | 1280 |
| 6 | Slave 5 | 0x0600 | 1536 |
| 7 | Slave 6 | 0x0700 | 1792 |
| 8 | Slave 7 (last) | 0x0800 | 2048 |
| 9–31 | RTU expansion modules | 0x0900 | 2304 |

### Extended function blocks (absolute addresses — no device offset)

| RTU Address | Role | Base Address (hex) | Base Address (dec) |
|---|---|---|---|
| 1 | Master extended functions | 0x2000 | 8192 |
| 2 | Slave 1 extended | 0x2100 | 8448 |
| 3 | Slave 2 extended | 0x2200 | 8704 |
| 4 | Slave 3 extended | 0x2300 | 8960 |
| 5 | Slave 4 extended | 0x2400 | 9216 |
| 6 | Slave 5 extended | 0x2500 | 9472 |
| 7 | Slave 6 extended | 0x2600 | 9728 |
| 8 | Slave 7 extended | 0x2700 | 9984 |

### Address calculation example

To read Temp.1 (offset 0x0019) on the Master (base 0x0100):
**absolute address = 0x0100 + 0x0019 = 0x0119 (281 dec)**

---

## 3. Register Map

> Legend: **ro** = read-only, **rw** = read-write.
> All offsets are relative to the device base address unless noted as absolute.
> Temperature/humidity values use ×0.1 scaling (e.g. 215 = 21.5 °C, 551 = 55.1 %RH).

### 3.1 Status Bit Registers (ro)

Each register uses bit 0..7 → thermostat 1..8.

| Offset | Name | Description |
|---|---|---|
| 0x0000 | regA | A-loop output. bit=1: energy demand |
| 0x0001 | regB | B-loop output. bit=1: energy demand |
| 0x0002 | Cond | Condensation warning. bit=1: cooling blocked in that zone |
| 0x0003 | Drying | Drying demand (option). bit=1: drying requested |
| 0x0004 | ECO | ECO mode. 1=ECO, 0=Normal |
| 0x0005 | Frost | Frost protection warning |
| 0x0006 | HC | Heating/Cooling state. 1=Cooling, 0=Heating |
| 0x0007 | Window | Window contact (option). bit=1: contact closed → window open |
| 0x0008 | NoConn | No thermostat connection (or not configured). bit=1 |
| 0x0009 | Lock | Keypad locked. 0=active, 1=locked |
| 0x000A | Relay | Relay regulation state (bit=1: relay energized). See bit layout below. **Not the physical relay state** — it's the logical demand before Forced/BMS-override is applied, so it can read 0 while the relay is genuinely on. For actual on/off state use REL0–REL9 (0x00F0–0x00F9, section 3.4) |
| 0x000B | Di | Digital inputs. See bit layout below |
| 0x000C | Signal | System signal bits. See bit layout below |
| 0x000D | Tpr | Timer/schedule active. bit=1: enabled, bits 0..7 → TH 1..8 |
| 0x000E | Live | Thermostat connection alive. bit=1 |
| 0x000F | Forced | Forced relay state (option). Same bit layout as Relay |

#### Relay register (0x000A) bit layout

| Bit | Terminal | Function |
|---|---|---|
| 0 | 1 | Heating relay |
| 1 | 3 | Valve output 1 |
| 2 | 4 | Valve output 2 |
| 3 | 5 | Valve output 3 |
| 4 | 8 | Valve output 4 |
| 5 | 9 | Valve output 5 |
| 6 | 10 | Valve output 6 |
| 7 | 11 | Valve output 7 |
| 8 | 12 | Valve output 8 |
| 9 | 2 | Cooling relay |
| 10–15 | — | Unused |

#### Di register (0x000B) bit layout

| Bit | Function |
|---|---|
| 0 | HC input (terminal 26) |
| 1 | ECO input (terminal 28) |
| 2 | ON input (terminal 29) |
| 3 | BMS-HC (last MODBUS H/C command) |
| 8 | Pump (any A or B loop active) |

#### Signal register (0x000C) bit layout

| Bit | Meaning (1 =) |
|---|---|
| 0 | Internal system function (Relay AND control) |
| 1 | Overheating (mixed water temp high) |
| 2 | Frost danger |
| 3 | Outdoor sensor fault |
| 4 | Water temp sensor fault |
| 5 | Mixing valve: opening (0 = valve at 0%) |
| 6 | BMS fault (Master only) |
| 7 | Heating energy sensor missing (ON input) |
| 8 | Output remote control active (TAP) |
| 9 | Reserved (firmware-dependent) |

---

### 3.2 Analog Registers (ro)

| Offset | Name | Unit / Scale | Description |
|---|---|---|---|
| 0x0010 | Ao | ×100 mV (0–1000 = 0–10 V) | Mixing valve output (terminal 31) |
| 0x0011 | Ai.0 | ×0.1 °C (error: 2220) | Water temperature sensor |
| 0x0012 | Ai.1 | ×0.1 °C (error: 2220) | Outdoor temperature sensor |
| 0x0013 | Ai.2 | mV (0–3300) | HC input, analog mode |
| 0x0014 | Ai.3 | mV (0–3300) | CE input, analog mode |
| 0x0015 | Ai.4 | ×0.1 °C (error: 2220) | ON input, heating energy sensor |
| 0x0016 | Ai.5 | mV (12000–16000) | DC 15V supply voltage |
| 0x0017 | Ai.6 | mV (0–16000) | Thermostat supply voltage |
| 0x0018 | Ai.7 | mV | I/O board reference voltage |

---

### 3.3 Thermostat Read-Only Registers (ro)

#### Measured Temperature (×0.1 °C)

| Offset | Name | Thermostat |
|---|---|---|
| 0x0019 | Temp.1 | 1 |
| 0x001A | Temp.2 | 2 |
| 0x001B | Temp.3 | 3 |
| 0x001C | Temp.4 | 4 |
| 0x001D | Temp.5 | 5 |
| 0x001E | Temp.6 | 6 |
| 0x001F | Temp.7 | 7 |
| 0x0020 | Temp.8 | 8 |

#### Measured Relative Humidity (×0.1 %RH)

| Offset | Name | Thermostat |
|---|---|---|
| 0x0021 | Rh.1 | 1 |
| 0x0022 | Rh.2 | 2 |
| 0x0023 | Rh.3 | 3 |
| 0x0024 | Rh.4 | 4 |
| 0x0025 | Rh.5 | 5 |
| 0x0026 | Rh.6 | 6 |
| 0x0027 | Rh.7 | 7 |
| 0x0028 | Rh.8 | 8 |

#### Calculated Dew Point (×0.1 °C)

| Offset | Name | Thermostat |
|---|---|---|
| 0x0029 | Dewp.1 | 1 |
| 0x002A | Dewp.2 | 2 |
| 0x002B | Dewp.3 | 3 |
| 0x002C | Dewp.4 | 4 |
| 0x002D | Dewp.5 | 5 |
| 0x002E | Dewp.6 | 6 |
| 0x002F | Dewp.7 | 7 |
| 0x0030 | Dewp.8 | 8 |

#### Active Setpoints (×0.1 °C, ro)

Each thermostat has 4 setpoints: Heating Normal (XaHN), Cooling Normal (XaCN), Heating ECO (XaHE), Cooling ECO (XaCE).

| TH | XaHN | XaCN | XaHE | XaCE |
|---|---|---|---|---|
| 1 | 0x0031 | 0x0032 | 0x0033 | 0x0034 |
| 2 | 0x0035 | 0x0036 | 0x0037 | 0x0038 |
| 3 | 0x0039 | 0x003A | 0x003B | 0x003C |
| 4 | 0x003D | 0x003E | 0x003F | 0x0040 |
| 5 | 0x0041 | 0x0042 | 0x0043 | 0x0044 |
| 6 | 0x0045 | 0x0046 | 0x0047 | 0x0048 |
| 7 | 0x0049 | 0x004A | 0x004B | 0x004C |
| 8 | 0x004D | 0x004E | 0x004F | 0x0050 |

#### System State Registers (ro)

| Offset | Name | Description |
|---|---|---|
| 0x0051 | HCmode | 0=Heating, 1=Cooling, >1=switchover in progress |
| 0x0052 | Tex | Effective outdoor temperature (×0.1 °C) |
| 0x0053 | XaW | Mixing valve calculated setpoint (×0.1 °C) |
| 0x0054 | PrgVer | Firmware version (0 on unreachable Slave) |
| 0x0055 | CfgVer.1 | Config file version low word |
| 0x0056 | CfgVer.2 | Config file version high word |
| 0x0057 | EffOut | Effective relay output = Relay OR Forced, incl. timing effects. **Do not use this for per-relay physical state** — it does not reflect BMS overrides or cross-unit driven relays; use REL0–REL9 (0x00F0–0x00F9) instead, confirmed via decompiled firmware to be the true per-relay physical output (also named `EffOut` internally, and matching the legacy JSON API's `"R<n>"` fields) |

---

### 3.4 Command Registers (rw)

#### System Commands

| Offset | Name | Description |
|---|---|---|
| 0x0058 | LSF | Light / Shader / FanCoil states (see iCON11 docs) |
| 0x0059 | VER | Config version last 4 digits. Write >0 → restart; write 65534 → thermostat reconnect (Master only) |
| 0x0060 | Override | Force relay on during regulation. Bit layout = Relay register. **Caution: OR'd with regulation output; do not use on thermostat-controlled outputs** |
| 0x0061 | Atemp | Alternative outdoor temperature (×0.1 °C, signed). Used when no outdoor sensor connected. **Master only** |
| 0x0062 | MasterHC | System H/C switch: 0=Heating, 1=Cooling. **Master only** |

#### Per-Thermostat State Commands

| Offset range | Name pattern | Description |
|---|---|---|
| 0x0063–0x006A | ECO.1–ECO.8 | ECO mode: 1=ECO, 0=Normal |
| 0x006B–0x0072 | LCK.1–LCK.8 | Keypad lock: 1=locked, 0=unlocked |
| 0x0073–0x007A | TPR.1–TPR.8 | Schedule/timer inactive: 0 (option) |
| 0x007B–0x0082 | FC.1–FC.8 | Fan-coil speed (0–100%) |

#### Setpoint Write Registers (×0.1 °C, range 50–350 = 5.0–35.0 °C)

Each thermostat has 4 writable setpoints: SpHN (Heat Normal), SpCN (Cool Normal), SpHE (Heat ECO), SpCE (Cool ECO).

| TH | SpHN | SpCN | SpHE | SpCE |
|---|---|---|---|---|
| 1 | 0x0083 | 0x0084 | 0x0085 | 0x0086 |
| 2 | 0x0087 | 0x0088 | 0x0089 | 0x008A |
| 3 | 0x008B | 0x008C | 0x008D | 0x008E |
| 4 | 0x008F | 0x0090 | 0x0091 | 0x0092 |
| 5 | 0x0093 | 0x0094 | 0x0095 | 0x0096 |
| 6 | 0x0097 | 0x0098 | 0x0099 | 0x009A |
| 7 | 0x009B | 0x009C | 0x009D | 0x009E |
| 8 | 0x009F | 0x00A0 | 0x00A1 | 0x00A2 |

#### Water Temperature Registers (×0.1 °C, range 0–1000 = 0–100.0 °C)

| Offset | Name | Description |
|---|---|---|
| 0x00A3 | Wtemp | Central water temperature override (Master only, address 0x01A3). Used for condensation protection and mixing valve when no local sensor |
| 0x00A4 | Stemp | Mixing valve remote setpoint. Ignored if outdoor sensor is connected |

#### BMS Extensions

| Offset range | Name | Description |
|---|---|---|
| 0x00B0–0x00B7 | THHC1–THHC8 | Per-thermostat H/C switch: 0=Heat (EEPROM), 1=Cool (EEPROM), 2=follow system H/C. **Master only** |
| 0x00B8 | TAP | Controllable output (JSON: "SW", Relay: S1,8). 0=off, 1=on |
| 0x00C0–0x00C7 | XA1–XA8 | BMS setpoint center value per thermostat |
| 0x00C8–0x00CF | SP1–SP8 | Current active setpoint per thermostat |
| 0x00D0–0x00D7 | ECO1–ECO8 | ECO mode setpoint offset (negative in heating, positive in cooling) |
| 0x00D8–0x00DF | LIM1–LIM8 | Max setpoint offset (actual setpoint ±LIM) |
| 0x00E0–0x00E7 | ZEB1–ZEB8 | Zero energy band. Heat setpoint = XA−ZEB, Cool setpoint = XA+ZEB |
| 0x00E9–0x00EF | RH1–RH8 | RH% control setpoint (currently deactivated) |
| 0x00F0–0x00F9 | REL0–REL9 | Per-relay override during regulation: 0=OFF, 1=ON (write). **On read, this is the true per-relay physical output state** (internal firmware field `EffOut`, confirmed via decompiled source, `iCON1v1.c`) — regulation demand OR'd with Forced, plus HC-mode masking, valve protection, and BMS cross-unit override. This is what this integration polls for relay on/off state; it matches the legacy JSON API's `"R<n>"` fields exactly, unlike the single-register `EffOut` at 0x0057 above |
| 0x00FA–0x00FF | REG1–REG6 | Per-thermostat local H/C switching enable: 1=enabled, 0=disabled (TH7–8 always enabled) |

---

### 3.5 Extended Function Registers (Absolute Addresses)

> These registers use **absolute** addresses — do **not** add a device base offset.

#### System Status

| Address | Name | R/W | Description |
|---|---|---|---|
| 0x2000 | CYCL | ro | I/O cycle counter (Master only) |
| 0x2001 | ISTATUS | ro | iCON status flags. bit 0: Master, bit=1: online |
| 0x2002 | BMS_TOUT | rw | Relay remote control timeout (default 3600 s = 1 h) |
| 0x2003 | BMS_REMOTE | ro | 0=relays in auto mode, 1=remote timeout active |

#### Relay Remote Control

> **Warning:** In remote-controlled mode, all regulation and protections (condensation, frost) are **disabled**. Remote control starts in auto mode (0) and remains active for 1 hour after the last write.

**RELMOD** — per-bit: 0=auto, 1=remote-controlled
**RELVAL** — per-bit: 0=relay off, 1=relay on (only effective when RELMOD bit=1)

Relay-to-bit mapping:

| Bit | Terminal | Function |
|---|---|---|
| 0 | 3 | Valve 1 |
| 1 | 4 | Valve 2 |
| 2 | 5 | Valve 3 |
| 3 | 8 | Valve 4 |
| 4 | 9 | Valve 5 |
| 5 | 10 | Valve 6 |
| 6 | 11 | Valve 7 |
| 7 | 12 | Valve 8 |
| 8–15 | — | Must be 0 |

| Address | Name | Description |
|---|---|---|
| 0x2010 | RELMOD1 | Master iCON relay mode |
| 0x2011 | RELMOD2 | Slave 1 relay mode |
| 0x2012 | RELMOD3 | Slave 2 relay mode |
| 0x2013 | RELMOD4 | Slave 3 relay mode |
| 0x2014 | RELMOD5 | Slave 4 relay mode |
| 0x2015 | RELMOD6 | Slave 5 relay mode |
| 0x2016 | RELMOD7 | Slave 6 relay mode |
| 0x2017 | RELMOD8 | Slave 7 relay mode |
| 0x2018 | RELVAL1 | Master iCON relay values |
| 0x2019 | RELVAL2 | Slave 1 relay values |
| 0x201A | RELVAL3 | Slave 2 relay values |
| 0x201B | RELVAL4 | Slave 3 relay values |
| 0x201C | RELVAL5 | Slave 4 relay values |
| 0x201D | RELVAL6 | Slave 5 relay values |
| 0x201E | RELVAL7 | Slave 6 relay values |
| 0x201F | RELVAL8 | Slave 7 relay values |

#### Per-Thermostat Individual H/C Switching Enable

> Only effective on Master thermostats. Slave thermostats follow Master H/C state. Remote H/C switching uses the THHC registers (0x00B0–0x00B7) if enabled in iCON config.

| Address | Name | Description |
|---|---|---|
| 0x2020 | IHC1 | TH1 local H/C switching: 1=enabled, 0=disabled |
| 0x2021 | IHC2 | TH2 |
| 0x2022 | IHC3 | TH3 |
| 0x2023 | IHC4 | TH4 |
| 0x2024 | IHC5 | TH5 |
| 0x2025 | IHC6 | TH6 |
| 0x2026 | IHC7 | TH7 |
| 0x2027 | IHC8 | TH8 |

---

## 4. Implementation Notes

1. **ro vs rw:** Reading an `rw` command register may return 0 or the current value depending on the function. For current state, read the corresponding `ro` register.
2. **Undefined registers:** Read returns 0; write executes silently but has no effect.
3. **Signed values:** Two's complement for negative temperatures (e.g. 0xFFFF = −0.1 °C).
4. **Master-only registers:** Atemp (0x0061), MasterHC (0x0062), Wtemp (0x00A3), THHC1–8 are only meaningful when written to the Master device. Slave devices ignore them. These commands are also ignored if the corresponding function is configured on a physical input.
5. **Override caution:** Override (0x0060) is OR'd with regulation output. Never use on thermostat-controlled valves — it can prevent valve closure during condensation risk. Cannot be used for H/C relay override.
6. **EEPROM save timing:** Parameters are persisted ~3–5 min after last modification. Power loss during this window reverts to previous saved state.
7. **Sensor error value:** 2220 (decimal) indicates a sensor fault for temperature inputs.
8. **Communication example:** To read TH2 temperature on Master: read 1 register at address 0x011A (= 0x0100 + 0x001A). Send hex `00 00 00 00 00 06 00 03 01 1A 00 01` to TCP:502. Response value 0x00D7 = 215 = 21.5 °C.
