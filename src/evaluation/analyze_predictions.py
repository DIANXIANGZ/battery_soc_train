"""Report prediction error by SOC band for a saved test_predictions.csv."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def analyze_predictions(predictions: Path) -> dict:
    actual, predicted = [], []
    with Path(predictions).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            actual.append(float(row["reference_soc"]))
            predicted.append(float(row["predicted_soc"]))
    actual = np.asarray(actual)
    predicted = np.asarray(predicted)
    error = predicted - actual

    report = {}
    edges = np.linspace(0.0, 1.0, 6)
    for index in range(5):
        low, high = edges[index], edges[index + 1]
        mask = (actual >= low) & ((actual < high) if index < 4 else (actual <= high))
        band_error = error[mask]
        if not len(band_error):
            report[f"{int(low*100)}-{int(high*100)}%"] = {
                "count": 0,
                "MAE_pct": None,
                "bias_pct": None,
            }
        else:
            report[f"{int(low*100)}-{int(high*100)}%"] = {
                "count": int(mask.sum()),
                "MAE_pct": float(np.mean(np.abs(band_error)) * 100),
                "bias_pct": float(np.mean(band_error) * 100),
            }
    return report


def write_analysis(predictions: Path, output: Path) -> dict:
    report = analyze_predictions(predictions)
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = write_analysis(args.predictions, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
