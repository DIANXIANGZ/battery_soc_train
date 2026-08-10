"""Centralized paths for data stored outside the PyCharm code project."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "paths.json"


@dataclass(frozen=True)
class DataCenterPaths:
    """Typed locations for all data assets in the SOC data center."""

    root: Path

    @classmethod
    def is_configured(cls, config_path: Path | None = None) -> bool:
        try:
            return cls.from_config(config_path).root.is_dir()
        except ValueError:
            return False

    @staticmethod
    def save_config(config_path: Path, root: Path) -> None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"data_center_root": str(root.resolve())}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def from_config(cls, config_path: Path | None = None) -> "DataCenterPaths":
        path = config_path or DEFAULT_CONFIG_PATH
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Data-center configuration does not exist: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Data-center configuration is not valid JSON: {path}") from exc
        value = payload.get("data_center_root")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Data-center configuration requires a non-empty 'data_center_root'.")
        return cls(Path(value))

    @property
    def training_csv(self) -> Path:
        return self.root / "02_训练数据" / "01_A123#3_SOC_30秒训练数据" / "a123_soc_30s.csv"

    @property
    def baseline_results_dir(self) -> Path:
        return self.root / "03_模型与实验结果" / "01_A123#3_基准模型与结果"

    @property
    def cross_cell_results_dir(self) -> Path:
        return self.root / "03_模型与实验结果" / "02_A123#5_跨电芯评估结果"

    @property
    def generalization_results_dir(self) -> Path:
        return self.root / "03_模型与实验结果" / "03_综合泛化验证"

    @property
    def platform_store_dir(self) -> Path:
        return self.root / "04_训练平台运行记录" / "01_SOC训练平台项目与运行记录"

    @property
    def external_data_dir(self) -> Path:
        return self.root / "05_外部评估数据"

    @property
    def research_training_dir(self) -> Path:
        return self.root / "02_训练数据" / "research_v1"

    @property
    def research_results_dir(self) -> Path:
        return self.root / "03_模型与实验结果" / "research_v1"

    @property
    def research_runs_dir(self) -> Path:
        return self.root / "04_训练平台运行记录" / "research_v1"

    @property
    def nasa_raw_dir(self) -> Path:
        return self.root / "01_原始数据" / "03_NASA_PCoE_多状态原始数据"

    @property
    def public_battery_raw_dir(self) -> Path:
        return self.root / "01_原始数据" / "04_公开电池数据集"

    @property
    def public_battery_canonical_dir(self) -> Path:
        return self.root / "02_训练数据" / "04_公开电池规范数据"

    @property
    def public_battery_reports_dir(self) -> Path:
        return self.root / "03_模型与实验结果" / "05_公开电池数据质量报告"

    @property
    def nasa_training_dir(self) -> Path:
        return self.root / "02_训练数据" / "02_NASA_五状态训练数据"

    @property
    def nasa_results_dir(self) -> Path:
        return self.root / "03_模型与实验结果" / "04_NASA_五状态模型与结果"

    @property
    def nasa_runs_dir(self) -> Path:
        return self.root / "04_训练平台运行记录" / "02_NASA_五状态训练平台记录"

    @property
    def nasa_improved_training_dir(self) -> Path:
        return self.root / "02_训练数据" / "03_NASA_生命周期训练数据"

    @property
    def nasa_lifecycle_results_dir(self) -> Path:
        return self.nasa_results_dir / "loco_lifecycle_v1"

    @property
    def a1235_processed_csv(self) -> Path:
        return (
            self.external_data_dir
            / "03_外部数据清单与处理后样本"
            / "cross_cell_a123_5_part1"
            / "a123_5_soc_30s.csv"
        )
