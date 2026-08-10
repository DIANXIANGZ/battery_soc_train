from __future__ import annotations

import unittest
from pathlib import Path

from src.project_paths import DataCenterPaths
from src.data_processing import prepare_a123_soc
from src.evaluation import evaluate_external_cell
from src.training import train_lstm


PROJECT = Path(__file__).resolve().parents[1]


class DefaultDataPathTests(unittest.TestCase):
    def test_training_parser_uses_data_center_defaults(self) -> None:
        paths = DataCenterPaths.from_config(PROJECT / "configs" / "paths.json")

        args = train_lstm.build_parser().parse_args([])

        self.assertEqual(paths.training_csv, args.data)
        self.assertEqual(paths.baseline_results_dir, args.results_dir)

    def test_explicit_training_paths_override_data_center_defaults(self) -> None:
        args = train_lstm.build_parser().parse_args(["--data", "X.csv", "--results-dir", "X-results"])

        self.assertEqual(Path("X.csv"), args.data)
        self.assertEqual(Path("X-results"), args.results_dir)

    def test_preprocessing_and_external_evaluation_use_configured_defaults(self) -> None:
        paths = DataCenterPaths.from_config(PROJECT / "configs" / "paths.json")

        prepare_args = prepare_a123_soc.build_parser().parse_args(["--input-dir", "raw"])
        evaluation_args = evaluate_external_cell.build_parser().parse_args(["--data", "target.csv", "--results-dir", "out"])

        self.assertEqual(paths.training_csv, prepare_args.output)
        self.assertEqual(paths.baseline_results_dir / "lstm_soc.pt", evaluation_args.model)


if __name__ == "__main__":
    unittest.main()
