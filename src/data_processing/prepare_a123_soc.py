"""Create a leakage-safe, SOC-labelled training table from A123 #3 Arbin exports.

The raw files have one time series split across many worksheet tabs.  The
charge and discharge capacity counters are used to make a Coulomb-counting
reference label within each test cycle:

    net_ah = charge_capacity - discharge_capacity
    SOC = (net_ah - cycle_min_net_ah) / cycle_net_ah_range

This is a reference label rather than an independently measured ground truth.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import openpyxl

from src.project_paths import DataCenterPaths


FIELDS = ["session", "cycle_index", "time_s", "voltage_v", "current_a", "dv_dt_v_s", "soc"]


def cells(row):
    """Return the needed Arbin columns, or None when a record is malformed."""
    try:
        time_s, cycle, current, voltage = float(row[1]), int(row[5]), float(row[6]), float(row[7])
        charge = float(row[8] or 0.0)
        discharge = float(row[9] or 0.0)
        dv_dt = float(row[12] or 0.0)
        return time_s, cycle, current, voltage, charge, discharge, dv_dt
    except (TypeError, ValueError, IndexError):
        return None


def sheets(book):
    return (book[name] for name in book.sheetnames if name != "Info")


def build_parser() -> argparse.ArgumentParser:
    paths = DataCenterPaths.from_config()
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path)
    p.add_argument("--input-file", type=Path, help="Process one workbook (useful for large archives).")
    p.add_argument("--output", type=Path, default=paths.training_csv)
    p.add_argument("--sample-seconds", type=float, default=30.0)
    p.add_argument("--include-incomplete", action="store_true")
    p.add_argument("--label-mode", choices=["legacy", "cycle-range"], default="cycle-range")
    return p


def main():
    args = build_parser().parse_args()

    if not args.input_dir and not args.input_file:
        raise SystemExit("Provide --input-dir or --input-file.")
    files = [args.input_file] if args.input_file else sorted(args.input_dir.glob("*.xlsx"))
    if not args.include_incomplete:
        files = [f for f in files if "incomplete" not in f.name.lower()]
    if not files:
        raise SystemExit("No Excel test files found.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for path in files:
            # Pass 1: characterize capacity counters for every cycle.
            max_capacity = defaultdict(float)
            net_range = {}
            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
            for sheet in sheets(book):
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    item = cells(row)
                    if item:
                        _, cycle, _, _, charge, discharge, _ = item
                        max_capacity[cycle] = max(max_capacity[cycle], charge, discharge)
                        net = charge - discharge
                        if cycle not in net_range:
                            net_range[cycle] = [net, net]
                        else:
                            net_range[cycle][0] = min(net_range[cycle][0], net)
                            net_range[cycle][1] = max(net_range[cycle][1], net)
            book.close()

            # Pass 2: generate labels and downsample without joining future data.
            kept_buckets = set()
            session_rows = 0
            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
            for sheet in sheets(book):
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    item = cells(row)
                    if not item:
                        continue
                    time_s, cycle, current, voltage, charge, discharge, dv_dt = item
                    if args.label_mode == "cycle-range":
                        low, high = net_range[cycle]
                        capacity = high - low
                    else:
                        low = 0.0
                        capacity = max_capacity[cycle]
                    if capacity < 0.1:
                        continue
                    bucket = (cycle, int(time_s // args.sample_seconds))
                    if bucket in kept_buckets:
                        continue
                    kept_buckets.add(bucket)
                    soc = max(0.0, min(1.0, ((charge - discharge) - low) / capacity))
                    writer.writerow({
                        "session": path.stem,
                        "cycle_index": cycle,
                        "time_s": f"{time_s:.3f}",
                        "voltage_v": f"{voltage:.6f}",
                        "current_a": f"{current:.6f}",
                        "dv_dt_v_s": f"{dv_dt:.9f}",
                        "soc": f"{soc:.6f}",
                    })
                    session_rows += 1
            book.close()
            total += session_rows
            print(f"{path.name}: {session_rows:,} labelled 30 s samples")
    print(f"Saved {total:,} samples to {args.output}")


if __name__ == "__main__":
    main()
