"""Portable PNG charts for the NASA five-state prediction experiment."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.training.train_multistate_lstm import TARGETS, TARGET_UNITS


WIDTH, HEIGHT = 980, 460
LEFT, RIGHT, TOP, BOTTOM = 74, 28, 86, 58
BLUE, ORANGE, TEXT, GRID = "#1967D2", "#E87326", "#1F2937", "#D1D5DB"


def _points(values: list[float], low: float, high: float) -> list[tuple[float, float]]:
    span, count = max(high - low, 1e-12), max(len(values) - 1, 1)
    return [(LEFT + (WIDTH - LEFT - RIGHT) * index / count, HEIGHT - BOTTOM - (HEIGHT - TOP - BOTTOM) * (value - low) / span) for index, value in enumerate(values)]


def _chart(run_dir: Path, target: str, rows: list[dict[str, str]], metrics: dict[str, object]) -> Path:
    actual = [float(row[f"reference_{target}"]) for row in rows[:800]]
    predicted = [float(row[f"predicted_{target}"]) for row in rows[:800]]
    if not actual:
        raise ValueError("Prediction table contains no rows.")
    low, high = min(actual + predicted), max(actual + predicted)
    margin = max((high - low) * 0.10, 0.01)
    low, high = low - margin, high + margin
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default()
    detail = metrics.get(target, {}) if isinstance(metrics, dict) else {}
    unit = TARGET_UNITS[target]
    subtitle = f"First {len(actual)} independent-test samples | MAE {float(detail.get('MAE', 0.0)):.4f} {unit} | RMSE {float(detail.get('RMSE', 0.0)):.4f} {unit}"
    draw.text((LEFT, 20), f"NASA five-state prediction: {target}", fill=TEXT, font=font)
    draw.text((LEFT, 43), subtitle, fill="#4B5563", font=font)
    draw.rectangle((LEFT, TOP, WIDTH - RIGHT, HEIGHT - BOTTOM), outline="#374151", width=1)
    for fraction in (0.25, 0.5, 0.75):
        y = HEIGHT - BOTTOM - (HEIGHT - TOP - BOTTOM) * fraction
        draw.line((LEFT, y, WIDTH - RIGHT, y), fill=GRID, width=1)
    draw.line(_points(actual, low, high), fill=BLUE, width=3)
    draw.line(_points(predicted, low, high), fill=ORANGE, width=3)
    draw.text((8, TOP - 4), f"{high:.3f}", fill=TEXT, font=font)
    draw.text((8, HEIGHT - BOTTOM - 4), f"{low:.3f}", fill=TEXT, font=font)
    legend_x = WIDTH - 250
    draw.line((legend_x, 22, legend_x + 28, 22), fill=BLUE, width=3)
    draw.text((legend_x + 36, 17), "Reference", fill=BLUE, font=font)
    draw.line((legend_x, 48, legend_x + 28, 48), fill=ORANGE, width=3)
    draw.text((legend_x + 36, 43), "LSTM estimate", fill=ORANGE, font=font)
    draw.text((WIDTH // 2 - 35, HEIGHT - 30), "Sample index", fill=TEXT, font=font)
    output_path = run_dir / f"{target}_prediction.png"
    image.save(output_path, format="PNG")
    return output_path


def build_multistate_charts(run_dir: Path) -> dict[str, Path]:
    """Build five prediction charts from a complete multi-state run."""

    run_dir = Path(run_dir)
    with (run_dir / "test_predictions.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    metrics = json.loads((run_dir / "metrics_by_target.json").read_text(encoding="utf-8"))
    return {target: _chart(run_dir, target, rows, metrics) for target in TARGETS}
