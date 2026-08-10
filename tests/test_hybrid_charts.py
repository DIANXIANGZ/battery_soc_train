from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.desktop.hybrid_charts import build_hybrid_charts


class HybridChartTests(unittest.TestCase):
    def test_hybrid_charts_write_five_four_fold_png_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            aggregate = {}
            for target in ("soc", "soe", "soh", "rul_cycles", "sot_5min_c"):
                aggregate[target] = {"mean_MAE": 0.1, "mean_RMSE": 0.2, "worst_fold": "test_RW12", "worst_MAE": 0.3, "fold_count": 4}
                if target in {"soh", "rul_cycles", "sot_5min_c"}:
                    aggregate[target].update({"baseline_mean_MAE": 0.4, "beats_baseline": True})
            (root / "aggregate_metrics.json").write_text(json.dumps(aggregate), encoding="utf-8")
            for cell in ("RW9", "RW10", "RW11", "RW12"):
                fold = root / f"test_{cell}"
                files = {
                    fold / "state" / "test_predictions.csv": ("soc", "soe"),
                    fold / "temperature" / "test_predictions.csv": ("sot_5min_c",),
                    fold / "lifecycle" / "test_predictions.csv": ("soh", "rul_cycles"),
                }
                for path, targets in files.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    fields = [field for target in targets for field in (f"reference_{target}", f"predicted_{target}")]
                    with path.open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
                        for index in range(4):
                            writer.writerow({field: 1.0 - index * 0.1 + (0.02 if field.startswith("predicted") else 0.0) for field in fields})

            charts = build_hybrid_charts(root)

            self.assertEqual(set(charts), {"soc", "soe", "soh", "rul_cycles", "sot_5min_c"})
            self.assertTrue(all(path.is_file() for path in charts.values()))


if __name__ == "__main__":
    unittest.main()
