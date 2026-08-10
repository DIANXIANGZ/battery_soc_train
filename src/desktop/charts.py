"""Create portable PNG charts from the artifacts saved by a SOC training run."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 980, 460
PADDING_LEFT, PADDING_RIGHT, PADDING_TOP, PADDING_BOTTOM = 74, 28, 86, 58
BLUE, ORANGE, TEXT, GRID = "#1967D2", "#E87326", "#1F2937", "#D1D5DB"


def _canvas(title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((PADDING_LEFT, 20), title, fill=TEXT, font=font)
    draw.text((PADDING_LEFT, 43), subtitle, fill="#4B5563", font=font)
    draw.rectangle((PADDING_LEFT, PADDING_TOP, WIDTH - PADDING_RIGHT, HEIGHT - PADDING_BOTTOM), outline="#374151", width=1)
    return image, draw


def _polyline(values: list[float], minimum: float, maximum: float) -> list[tuple[float, float]]:
    if not values:
        return []
    span, count = max(maximum - minimum, 1e-12), max(len(values) - 1, 1)
    return [
        (
            PADDING_LEFT + (WIDTH - PADDING_LEFT - PADDING_RIGHT) * index / count,
            HEIGHT - PADDING_BOTTOM - (HEIGHT - PADDING_TOP - PADDING_BOTTOM) * (value - minimum) / span,
        )
        for index, value in enumerate(values)
    ]


def _draw_prediction_chart(run_dir: Path, output_path: Path) -> None:
    with (run_dir / "test_predictions.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))[:800]
    actual = [float(row["reference_soc"]) for row in rows]
    predicted = [float(row["predicted_soc"]) for row in rows]
    metrics_path = run_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.is_file() else {}
    subtitle = "Independent test session | first 800 samples"
    if "MAE_pct" in metrics and "RMSE_pct" in metrics:
        subtitle += f" | MAE {float(metrics['MAE_pct']):.2f}% | RMSE {float(metrics['RMSE_pct']):.2f}%"
    image, draw = _canvas("SOC prediction compared with reference", subtitle)
    for fraction in (0.25, 0.5, 0.75):
        y = HEIGHT - PADDING_BOTTOM - (HEIGHT - PADDING_TOP - PADDING_BOTTOM) * fraction
        draw.line((PADDING_LEFT, y, WIDTH - PADDING_RIGHT, y), fill=GRID, width=1)
    draw.line(_polyline(actual, 0.0, 1.0), fill=BLUE, width=3)
    draw.line(_polyline(predicted, 0.0, 1.0), fill=ORANGE, width=3)
    font, legend_x = ImageFont.load_default(), WIDTH - 250
    draw.text((16, PADDING_TOP - 4), "100%", fill=TEXT, font=font)
    draw.text((32, HEIGHT - PADDING_BOTTOM - 4), "0%", fill=TEXT, font=font)
    draw.line((legend_x, 22, legend_x + 28, 22), fill=BLUE, width=3)
    draw.text((legend_x + 36, 17), "Reference SOC", fill=BLUE, font=font)
    draw.line((legend_x, 48, legend_x + 28, 48), fill=ORANGE, width=3)
    draw.text((legend_x + 36, 43), "LSTM estimate", fill=ORANGE, font=font)
    draw.text((WIDTH // 2 - 35, HEIGHT - 30), "Sample index", fill=TEXT, font=font)
    image.save(output_path, format="PNG")


def _draw_validation_loss_chart(run_dir: Path, output_path: Path) -> None:
    history = json.loads((run_dir / "training_history.json").read_text(encoding="utf-8"))
    validation_values = [float(item["validation_mse"]) for item in history]
    training_values = [float(item["training_mse"]) for item in history if "training_mse" in item]
    epochs = [int(item["epoch"]) for item in history]
    all_values = validation_values + training_values
    minimum, maximum = min(all_values), max(all_values)
    margin = max((maximum - minimum) * 0.12, 0.000001)
    image, draw = _canvas("Training and validation loss", "A widening gap can indicate overfitting")
    for fraction in (0.25, 0.5, 0.75):
        y = HEIGHT - PADDING_BOTTOM - (HEIGHT - PADDING_TOP - PADDING_BOTTOM) * fraction
        draw.line((PADDING_LEFT, y, WIDTH - PADDING_RIGHT, y), fill=GRID, width=1)
    if training_values:
        draw.line(_polyline(training_values, minimum - margin, maximum + margin), fill=BLUE, width=3)
    draw.line(_polyline(validation_values, minimum - margin, maximum + margin), fill="#7C3AED", width=3)
    font = ImageFont.load_default()
    draw.text((10, PADDING_TOP - 4), f"{maximum + margin:.5f}", fill=TEXT, font=font)
    draw.text((10, HEIGHT - PADDING_BOTTOM - 4), f"{minimum - margin:.5f}", fill=TEXT, font=font)
    draw.text((PADDING_LEFT, HEIGHT - 46), f"Epoch {epochs[0]}", fill=TEXT, font=font)
    draw.text((WIDTH - PADDING_RIGHT - 55, HEIGHT - 46), f"Epoch {epochs[-1]}", fill=TEXT, font=font)
    if training_values:
        draw.line((WIDTH - 260, 22, WIDTH - 232, 22), fill=BLUE, width=3)
        draw.text((WIDTH - 224, 17), "Training MSE", fill=BLUE, font=font)
    draw.line((WIDTH - 260, 48, WIDTH - 232, 48), fill="#7C3AED", width=3)
    draw.text((WIDTH - 224, 43), "Validation MSE", fill="#7C3AED", font=font)
    draw.text((WIDTH // 2 - 42, HEIGHT - 22), "Training epoch", fill=TEXT, font=font)
    image.save(output_path, format="PNG")


def ensure_run_charts(run_dir: Path) -> dict[str, Path]:
    """Return existing or newly generated PNG charts for one run directory."""
    run_dir = Path(run_dir)
    charts: dict[str, Path] = {}
    prediction_path = run_dir / "soc_prediction.png"
    if prediction_path.is_file() or (run_dir / "test_predictions.csv").is_file():
        if not prediction_path.is_file():
            _draw_prediction_chart(run_dir, prediction_path)
        charts["prediction"] = prediction_path
    validation_path = run_dir / "validation_loss.png"
    if validation_path.is_file() or (run_dir / "training_history.json").is_file():
        if not validation_path.is_file():
            _draw_validation_loss_chart(run_dir, validation_path)
        charts["validation_loss"] = validation_path
    return charts
