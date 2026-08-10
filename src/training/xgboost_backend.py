"""Isolated XGBoost worker to avoid PyTorch/OpenMP runtime collisions on macOS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--estimators", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--runtime-report", type=Path)
    args = parser.parse_args()
    if "torch" in sys.modules:
        raise RuntimeError("XGBoost backend must run in a clean interpreter without torch loaded")
    sys.modules["sklearn"] = None
    import xgboost as xgb

    arrays = np.load(args.input)
    train_y = arrays["train_y"]
    if train_y.ndim == 1:
        train_y = train_y[:, None]
    test_matrix = xgb.DMatrix(arrays["test_x"])
    predictions = []
    for target_index in range(train_y.shape[1]):
        train_matrix = xgb.DMatrix(arrays["train_x"], label=train_y[:, target_index])
        model = xgb.train(
            {
                "objective": "reg:squarederror",
                "max_depth": 6,
                "eta": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "seed": args.seed,
                "nthread": 1,
                "tree_method": "hist",
            },
            train_matrix,
            num_boost_round=args.estimators,
        )
        predictions.append(model.predict(test_matrix))
    np.save(args.output, np.column_stack(predictions))

    if args.runtime_report:
        from threadpoolctl import threadpool_info

        args.runtime_report.write_text(json.dumps({
            "torch_loaded": "torch" in sys.modules,
            "sklearn_loaded": any(
                (name == "sklearn" or name.startswith("sklearn.")) and module is not None
                for name, module in sys.modules.items()
            ),
            "openmp_runtimes": [
                entry.get("filepath")
                for entry in threadpool_info()
                if entry.get("user_api") == "openmp"
            ],
        }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
