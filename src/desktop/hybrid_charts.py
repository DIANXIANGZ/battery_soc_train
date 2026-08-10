"""Four-cell comparison charts for the hybrid NASA workflow."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


TARGETS = ("soc", "soe", "soh", "rul_cycles", "sot_5min_c")
CELLS = ("RW9", "RW10", "RW11", "RW12")


def _prediction_path(root: Path, cell: str, target: str) -> Path:
    component = "lifecycle" if target in {"soh", "rul_cycles"} else ("temperature" if target == "sot_5min_c" else "state")
    return root / f"test_{cell}" / component / "test_predictions.csv"


def _scaled_points(values: list[float], box: tuple[int, int, int, int], low: float, high: float) -> list[tuple[float, float]]:
    left, top, right, bottom = box
    span, count = max(high - low, 1e-12), max(len(values) - 1, 1)
    return [(left + (right - left) * i / count, bottom - (bottom - top) * (value - low) / span) for i, value in enumerate(values)]


def _draw_target(root: Path, target: str, aggregate: dict[str, object]) -> Path:
    image = Image.new("RGB", (1200, 800), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default()
    status = ""
    if "beats_baseline" in aggregate:
        status = " | beats baseline" if aggregate["beats_baseline"] else " | DOES NOT beat baseline"
    draw.text((40, 22), f"NASA hybrid: {target} | macro MAE {float(aggregate['mean_MAE']):.4f} | worst {aggregate['worst_fold']}{status}", fill="#1F2937", font=font)
    for index, cell in enumerate(CELLS):
        path = _prediction_path(root, cell, target)
        if not path.is_file():
            raise ValueError(f"Incomplete hybrid evidence: {path}")
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise ValueError(f"Prediction file contains no rows: {path}")
        reference = [float(row[f"reference_{target}"]) for row in rows]
        predicted = [float(row[f"predicted_{target}"]) for row in rows]
        baseline_key = f"baseline_{target}"
        baseline = [float(row[baseline_key]) for row in rows] if baseline_key in rows[0] else []
        column, row_index = index % 2, index // 2
        left, top = 55 + column * 585, 90 + row_index * 345
        box = (left + 45, top + 30, left + 540, top + 285)
        all_values = reference + predicted + baseline
        low, high = min(all_values), max(all_values)
        margin = max((high - low) * 0.08, 1e-3); low -= margin; high += margin
        draw.text((left, top), f"Held-out {cell}", fill="#111827", font=font)
        draw.rectangle(box, outline="#6B7280")
        draw.line(_scaled_points(reference, box, low, high), fill="#1967D2", width=2)
        draw.line(_scaled_points(predicted, box, low, high), fill="#E87326", width=2)
        if baseline:
            draw.line(_scaled_points(baseline, box, low, high), fill="#6B7280", width=1)
    output = root / f"{target}_prediction.png"
    image.save(output, "PNG")
    return output


def build_hybrid_charts(run_dir: Path) -> dict[str, Path]:
    root = Path(run_dir)
    aggregate_path = root / "aggregate_metrics.json"
    if not aggregate_path.is_file():
        raise ValueError("Hybrid aggregate metrics are missing.")
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    if not set(TARGETS).issubset(aggregate):
        raise ValueError("Hybrid aggregate metrics are incomplete.")
    return {target: _draw_target(root, target, aggregate[target]) for target in TARGETS}
