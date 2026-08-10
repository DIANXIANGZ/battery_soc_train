"""Read, validate, and normalize user-supplied battery datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.custom_training.algorithms import algorithm_keys


SUPPORTED_SUFFIXES = frozenset({".csv", ".xlsx", ".xls"})
ALGORITHMS = algorithm_keys()
ROLE_KEYS = frozenset({
    "cell_id",
    "session_id",
    "cycle_id",
    "condition_id",
    "rul_observed",
    "eol_provenance",
})
STRING_ROLE_KEYS = frozenset({"cell_id", "session_id", "condition_id", "eol_provenance"})
NUMERIC_ROLE_KEYS = frozenset({"cycle_id", "rul_observed"})


@dataclass(frozen=True)
class CustomDatasetConfig:
    source_path: Path
    sheet_name: str | None
    time_column: str | None
    feature_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    algorithm: str
    role_columns: tuple[tuple[str, str], ...] = ()


def canonical_role_mapping(config: CustomDatasetConfig) -> dict[str, str]:
    """Return a validated canonical-role to source-column mapping."""
    mapping: dict[str, str] = {}
    source_columns: set[str] = set()
    data_columns = set(config.feature_columns) | set(config.target_columns)
    for role, source_column in config.role_columns:
        if role not in ROLE_KEYS:
            raise ValueError(f"不支持的字段角色：{role}")
        if role in mapping:
            raise ValueError(f"字段角色不能重复：{role}")
        if source_column in source_columns:
            raise ValueError(f"同一源字段不能映射到多个角色：{source_column}")
        if source_column in data_columns:
            raise ValueError(f"角色字段不能同时作为特征或目标：{source_column}")
        mapping[role] = source_column
        source_columns.add(source_column)
    return mapping


def _require_supported_path(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("仅支持 CSV、XLSX 或 XLS 数据文件。")
    if not path.is_file():
        raise ValueError(f"数据文件不存在：{path}")
    return path


def _excel_engine(path: Path) -> str:
    return "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"


def list_sheet_names(path: Path) -> tuple[str, ...]:
    path = _require_supported_path(path)
    if path.suffix.lower() == ".csv":
        return ()
    try:
        with pd.ExcelFile(path, engine=_excel_engine(path)) as workbook:
            return tuple(str(name) for name in workbook.sheet_names)
    except (OSError, ValueError, ImportError) as error:
        raise ValueError(f"无法读取 Excel 工作簿：{error}") from error


def _read_frame(path: Path, sheet_name: str | None) -> pd.DataFrame:
    path = _require_supported_path(path)
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        return pd.read_excel(path, sheet_name=sheet_name or 0, engine=_excel_engine(path))
    except (OSError, UnicodeError, ValueError, ImportError) as error:
        raise ValueError(f"无法读取数据文件：{error}") from error


def read_headers(path: Path, sheet_name: str | None = None) -> tuple[str, ...]:
    frame = _read_frame(path, sheet_name)
    headers = tuple(str(column) for column in frame.columns)
    if not headers:
        raise ValueError("数据文件不包含字段名。")
    return headers


def _selected_columns(config: CustomDatasetConfig, columns: tuple[str, ...]) -> tuple[str, ...]:
    if config.algorithm not in ALGORITHMS:
        raise ValueError(f"不支持的训练算法：{config.algorithm}")
    if not config.feature_columns:
        raise ValueError("请至少选择一个特征列。")
    if not config.target_columns:
        raise ValueError("请至少选择一个预测目标列。")
    role_mapping = canonical_role_mapping(config)
    role_sources = tuple(role_mapping.values())
    selected = tuple(
        dict.fromkeys(
            column
            for column in (*role_sources, config.time_column, *config.feature_columns, *config.target_columns)
            if column
        )
    )
    non_role_selected = tuple(
        column for column in (config.time_column, *config.feature_columns, *config.target_columns) if column
    )
    if len(non_role_selected) != len(set(non_role_selected)):
        raise ValueError("时间列、特征列和目标列不能重复。")
    missing = [column for column in selected if column not in columns]
    if missing:
        raise ValueError(f"数据文件缺少所选字段：{', '.join(missing)}")
    return selected


def validate_and_export(config: CustomDatasetConfig, output_path: Path, *, minimum_rows: int = 30) -> dict[str, object]:
    """Export selected columns after strict numeric validation of features and targets."""
    if minimum_rows < 1:
        raise ValueError("最小数据行数必须为正数。")
    frame = _read_frame(config.source_path, config.sheet_name)
    columns = tuple(str(column) for column in frame.columns)
    frame.columns = columns
    selected = _selected_columns(config, columns)
    normalized = frame.loc[:, selected].copy()
    role_mapping = canonical_role_mapping(config)
    normalized = normalized.rename(columns={source: role for role, source in role_mapping.items()})
    for role in STRING_ROLE_KEYS.intersection(role_mapping):
        normalized[role] = normalized[role].map(lambda value: str(value) if pd.notna(value) else value)
    for role in NUMERIC_ROLE_KEYS.intersection(role_mapping):
        original = normalized[role]
        converted = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & converted.isna()
        if invalid.any():
            raise ValueError(f"角色列“{role}”包含无法转换为数值的数据。")
        normalized[role] = converted
    for column in (*config.feature_columns, *config.target_columns):
        original = normalized[column]
        converted = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & converted.isna()
        if invalid.any():
            raise ValueError(f"列“{column}”包含无法转换为数值的数据。")
        normalized[column] = converted
    normalized = normalized.dropna(subset=[*config.feature_columns, *config.target_columns])
    if len(normalized) < minimum_rows:
        raise ValueError(f"有效数据仅 {len(normalized)} 行，至少需要 {minimum_rows} 行。")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_path, index=False, encoding="utf-8")
    return {"row_count": int(len(normalized)), "headers": tuple(str(column) for column in normalized.columns)}
