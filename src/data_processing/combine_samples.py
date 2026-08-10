"""Combine per-workbook SOC sample files into one training table."""
import argparse
import csv
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    files = sorted(args.input_dir.glob("*.csv"))
    if not files:
        raise SystemExit("No CSV inputs found.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with args.output.open("w", newline="", encoding="utf-8") as out:
        writer = None
        for file in files:
            with file.open(newline="", encoding="utf-8") as inp:
                reader = csv.DictReader(inp)
                if writer is None:
                    writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
                    writer.writeheader()
                for row in reader:
                    writer.writerow(row)
                    rows += 1
    print(f"Combined {len(files)} files and {rows:,} samples.")


if __name__ == "__main__":
    main()
