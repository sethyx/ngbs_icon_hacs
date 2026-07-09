#!/usr/bin/env python3
"""Compare the legacy (JSON) and new (Modbus) iCON datasets.

Fetches both datasets live (or loads two saved canonical JSON files) and reports
any field that does not match. Numeric fields are compared within a tolerance;
booleans must match exactly. ``name`` fields are ignored (Modbus has no names).

This is the acceptance gate for the Modbus library and the tool used to pin the
relay R<n> -> bit mapping. Exits non-zero if any mismatch is found.

Usage:
    python tools/compare.py --host 192.168.1.50 --sysid ABCD1234
    python tools/compare.py --old old.json --new new.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modbus_client import IconModbusClient  # noqa: E402
from names import IconJsonClient, raw_to_canonical  # noqa: E402

NUMERIC_TH_FIELDS = (
    "temp",
    "rh",
    "dew",
    "target",
    "sp_heat_normal",
    "sp_cool_normal",
    "sp_heat_eco",
    "sp_cool_eco",
)
BOOL_TH_FIELDS = ("eco", "demand", "cooling")


class Report:
    """Collects mismatches and info notes."""

    def __init__(self, tolerance: float) -> None:
        self.tolerance = tolerance
        self.mismatches: list[str] = []
        self.notes: list[str] = []

    def num(self, path: str, old, new) -> None:
        if old is None and new is None:
            return
        if old is None or new is None:
            # A field only one side can produce (e.g. outdoor_temp) is a note.
            self.notes.append(f"{path}: old={old} new={new} (only one side)")
            return
        if abs(old - new) > self.tolerance:
            self.mismatches.append(f"{path}: old={old} new={new} (Δ={old - new:+.2f})")

    def boolean(self, path: str, old, new) -> None:
        if old != new:
            self.mismatches.append(f"{path}: old={old} new={new}")

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def compare(old: dict, new: dict, tolerance: float) -> Report:
    """Diff two canonical datasets."""
    r = Report(tolerance)

    r.boolean("system.cooling", old["system"]["cooling"], new["system"]["cooling"])
    r.boolean("system.pump", old["system"]["pump"], new["system"]["pump"])
    r.num("system.water_temp", old["system"]["water_temp"], new["system"]["water_temp"])
    r.num(
        "system.outdoor_temp",
        old["system"]["outdoor_temp"],
        new["system"]["outdoor_temp"],
    )

    old_icons, new_icons = old["icons"], new["icons"]
    for icon in sorted(set(old_icons) | set(new_icons)):
        if icon not in old_icons or icon not in new_icons:
            r.note(f"icon {icon} present only in {'old' if icon in old_icons else 'new'}")
            continue
        o, n = old_icons[icon], new_icons[icon]
        r.num(f"icon{icon}.mixing_valve_pct", o["mixing_valve_pct"], n["mixing_valve_pct"])

        o_th, n_th = o["thermostats"], n["thermostats"]
        for th in sorted(set(o_th) | set(n_th)):
            if th not in o_th or th not in n_th:
                side = "old" if th in o_th else "new"
                r.note(f"thermostat {th} present only in {side}")
                continue
            for field in NUMERIC_TH_FIELDS:
                r.num(f"th{th}.{field}", o_th[th][field], n_th[th][field])
            for field in BOOL_TH_FIELDS:
                r.boolean(f"th{th}.{field}", o_th[th][field], n_th[th][field])

        # Relays: only compare those configured on the legacy side (have names).
        o_relay, n_relay = o["relays"], n["relays"]
        for rid in sorted(o_relay):
            if rid not in n_relay:
                r.note(f"relay {icon}/{rid} missing from new dataset")
                continue
            name = o_relay[rid].get("name") or rid
            r.boolean(f"icon{icon}.{rid} ({name})", o_relay[rid]["on"], n_relay[rid]["on"])

    return r


async def fetch_both(host: str, sysid: str) -> tuple[dict, dict]:
    """Fetch legacy and Modbus datasets from a live controller."""
    json_client = IconJsonClient(host, sysid)
    raw = await json_client.async_get_raw()
    old = raw_to_canonical(raw)
    from names import extract_inventory  # local import to keep top clean

    inventory = extract_inventory(raw)

    modbus = IconModbusClient(host)
    try:
        await modbus.async_connect()
        new = await modbus.async_get_data(inventory)
    finally:
        await modbus.async_close()
    return old, new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="Controller IP (live compare)")
    parser.add_argument("--sysid", help="System ID (live compare)")
    parser.add_argument("--old", help="Path to a saved canonical JSON (legacy)")
    parser.add_argument("--new", help="Path to a saved canonical JSON (modbus)")
    parser.add_argument("--tolerance", type=float, default=0.1)
    args = parser.parse_args()

    if args.old and args.new:
        with open(args.old, encoding="utf-8") as f:
            old = json.load(f)
        with open(args.new, encoding="utf-8") as f:
            new = json.load(f)
    elif args.host and args.sysid:
        old, new = asyncio.run(fetch_both(args.host, args.sysid))
    else:
        parser.error("provide either --old/--new files or --host/--sysid")

    r = compare(old, new, args.tolerance)

    if r.notes:
        print("Notes:")
        for note in r.notes:
            print(f"  - {note}")
    if r.mismatches:
        print(f"\nMISMATCHES ({len(r.mismatches)}):")
        for m in r.mismatches:
            print(f"  ✗ {m}")
        return 1

    print("\n✓ Datasets match (within tolerance).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
