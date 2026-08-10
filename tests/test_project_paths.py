from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.project_paths import DataCenterPaths


class DataCenterPathsTests(unittest.TestCase):
    def test_save_config_round_trips_a_data_center_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "数据中心"
            config = Path(temp_dir) / "paths.json"

            DataCenterPaths.save_config(config, root)

            self.assertEqual(DataCenterPaths.from_config(config).root, root.resolve())

    def test_is_configured_requires_an_existing_data_center(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "数据中心"
            config = Path(temp_dir) / "paths.json"

            self.assertFalse(DataCenterPaths.is_configured(config))
            root.mkdir()
            DataCenterPaths.save_config(config, root)

            self.assertTrue(DataCenterPaths.is_configured(config))

    def test_paths_read_the_configured_data_center(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "数据中心"
            config = Path(temp_dir) / "paths.json"
            config.write_text(json.dumps({"data_center_root": str(root)}), encoding="utf-8")

            paths = DataCenterPaths.from_config(config)

            self.assertEqual(
                root / "02_训练数据" / "01_A123#3_SOC_30秒训练数据" / "a123_soc_30s.csv",
                paths.training_csv,
            )
            self.assertEqual(
                root / "03_模型与实验结果" / "03_综合泛化验证",
                paths.generalization_results_dir,
            )
            self.assertEqual(
                root / "05_外部评估数据" / "03_外部数据清单与处理后样本"
                / "cross_cell_a123_5_part1" / "a123_5_soc_30s.csv",
                paths.a1235_processed_csv,
            )

    def test_missing_data_center_configuration_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "paths.json"
            config.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "data_center_root"):
                DataCenterPaths.from_config(config)

    def test_research_v1_paths_are_isolated_from_existing_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data-center"
            config = Path(temp_dir) / "paths.json"
            config.write_text(json.dumps({"data_center_root": str(root)}), encoding="utf-8")
            paths = DataCenterPaths.from_config(config)
            self.assertEqual(root / "02_训练数据" / "research_v1", paths.research_training_dir)
            self.assertEqual(root / "03_模型与实验结果" / "research_v1", paths.research_results_dir)
            self.assertEqual(root / "04_训练平台运行记录" / "research_v1", paths.research_runs_dir)


    def test_nasa_multistate_paths_are_isolated_from_soc_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data-center"
            config = Path(temp_dir) / "paths.json"
            config.write_text(json.dumps({"data_center_root": str(root)}), encoding="utf-8")

            paths = DataCenterPaths.from_config(config)

            self.assertEqual(
                root / "01_原始数据" / "03_NASA_PCoE_多状态原始数据",
                paths.nasa_raw_dir,
            )
            self.assertEqual(
                root / "02_训练数据" / "02_NASA_五状态训练数据",
                paths.nasa_training_dir,
            )
            self.assertEqual(
                root / "03_模型与实验结果" / "04_NASA_五状态模型与结果",
                paths.nasa_results_dir,
            )
            self.assertEqual(
                root / "04_训练平台运行记录" / "02_NASA_五状态训练平台记录",
                paths.nasa_runs_dir,
            )
            self.assertNotEqual(paths.nasa_training_dir, paths.training_csv.parent)
            self.assertNotEqual(paths.nasa_results_dir, paths.baseline_results_dir)


if __name__ == "__main__":
    unittest.main()
