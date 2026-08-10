# 自定义数据集与算法训练 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让桌面端导入 CSV/XLSX/XLS 电池时序数据，配置特征与一个或多个数值目标，并以 LSTM、GRU、XGBoost 或 Transformer 完成独立训练。

**Architecture:** 新增 `src/custom_training` 负责配置、文件读取、校验和格式规范化；新增 `src/training/train_custom.py` 以一个稳定 CLI 路由四种算法。`PlatformStore` 保存自定义项目的配置，桌面端仅负责导入向导、项目选择和命令启动；内置项目保留原命令与训练器。

**Tech Stack:** Python 3、Tkinter、pandas、openpyxl、xlrd、NumPy、scikit-learn、XGBoost、PyTorch、pytest。

## Global Constraints

- 支持 `.csv`、`.xlsx`、`.xls`；Excel 必须允许选择工作表。
- 必须至少选择一个特征列和一个数值目标列；时间列可选；导入时至少保留 30 行，训练器再按所选窗口验证可切分样本数。
- 算法名称固定为 `lstm`、`gru`、`xgboost`、`transformer`；默认 `lstm`。
- SOC/SOE/SOT 在导入界面推荐 LSTM，RUL 推荐 XGBoost；推荐不得限制用户选择。
- 所有自定义训练输出 `metrics.json`、`metrics_by_target.json`、`test_predictions.csv`、`run_config.json` 和 `training_history.json`。
- 原有 A123、NASA 五状态、NASA 五状态（改进）的项目、命令与训练器不改变。
- 当前工作目录没有 Git 元数据；每一项的“提交”步骤在实际环境中记录为跳过，不执行伪提交。

---

## File structure

- Create: `src/custom_training/__init__.py` — 自定义训练公共 API。
- Create: `src/custom_training/dataset.py` — 格式检查、表头读取、工作表发现、列映射校验与规范 CSV 导出。
- Create: `src/training/train_custom.py` — 通用 CLI、时序切分、四个算法、统一训练工件输出。
- Modify: `src/platform/platform_core.py` — 自定义项目持久化与安全训练命令构造。
- Modify: `src/desktop/app.py` — 导入向导、自定义项目的训练页和通用结果展示。
- Modify: `requirements.txt` — 加入 `pandas`、`xlrd` 和 `xgboost`。
- Create: `tests/test_custom_dataset.py` — 文件读取、映射和错误信息。
- Create: `tests/test_train_custom.py` — 路由、最小训练与输出工件。
- Modify: `tests/test_platform_core.py` — 自定义项目和命令构造。
- Modify: `tests/test_desktop_app.py` — 导入入口、推荐逻辑和自定义训练路由。

### Task 1: 自定义数据读取、规范化和配置验证

**Files:**
- Create: `src/custom_training/__init__.py`
- Create: `src/custom_training/dataset.py`
- Create: `tests/test_custom_dataset.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces `CustomDatasetConfig(source_path: Path, sheet_name: str | None, time_column: str | None, feature_columns: tuple[str, ...], target_columns: tuple[str, ...], algorithm: str)`.
- Produces `list_sheet_names(path: Path) -> tuple[str, ...]`, `read_headers(path: Path, sheet_name: str | None = None) -> tuple[str, ...]`, `validate_and_export(config: CustomDatasetConfig, output_path: Path) -> dict[str, object]`.
- `validate_and_export` writes a UTF-8 `custom_training.csv` with selected source columns, rejects unsupported formats, unreadable worksheets, missing selections, non-numeric feature/target cells, and fewer than 30 valid rows. The trainer rejects a selected window that cannot produce train/validation/test sequences.

- [ ] **Step 1: Write failing data-contract tests**

```python
def test_csv_mapping_exports_only_time_features_and_targets(tmp_path: Path) -> None:
    source = tmp_path / "cell.csv"
    source.write_text("time,v,i,soc,note\n" + "\n".join(f"{i},3.7,1.0,0.8,a" for i in range(40)), encoding="utf-8")
    config = CustomDatasetConfig(source, None, "time", ("v", "i"), ("soc",), "lstm")

    result = validate_and_export(config, tmp_path / "custom_training.csv", minimum_rows=30)

    assert result["row_count"] == 40
    assert (tmp_path / "custom_training.csv").read_text(encoding="utf-8").splitlines()[0] == "time,v,i,soc"

def test_xlsx_exposes_sheet_names_and_legacy_xls_is_accepted(tmp_path: Path) -> None:
    workbook = tmp_path / "cell.xlsx"
    # Create sheets named "cycles" and "labels" with openpyxl.
    assert list_sheet_names(workbook) == ("cycles", "labels")
    assert ".xls" in SUPPORTED_SUFFIXES

def test_invalid_non_numeric_target_names_the_column(tmp_path: Path) -> None:
    config = CustomDatasetConfig(tmp_path / "bad.csv", None, None, ("v",), ("soc",), "lstm")
    with pytest.raises(ValueError, match="soc.*数值"):
        validate_and_export(config, tmp_path / "out.csv", minimum_rows=1)
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_custom_dataset.py -v`

Expected: FAIL because `src.custom_training.dataset` does not exist.

- [ ] **Step 3: Implement the minimal data module and dependencies**

```python
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}
ALGORITHMS = ("lstm", "gru", "xgboost", "transformer")

@dataclass(frozen=True)
class CustomDatasetConfig:
    source_path: Path
    sheet_name: str | None
    time_column: str | None
    feature_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    algorithm: str

def validate_and_export(config: CustomDatasetConfig, output_path: Path, *, minimum_rows: int) -> dict[str, object]:
    frame = _read_frame(config.source_path, config.sheet_name)
    selected = _validate_selection(frame.columns, config)
    numeric = frame.loc[:, selected].copy()
    for column in [*config.feature_columns, *config.target_columns]:
        numeric[column] = pandas.to_numeric(numeric[column], errors="coerce")
        if numeric[column].isna().any():
            raise ValueError(f"列“{column}”包含无法转换为数值的数据。")
    numeric = numeric.dropna()
    if len(numeric) < minimum_rows:
        raise ValueError(f"有效数据仅 {len(numeric)} 行，至少需要 {minimum_rows} 行。")
    numeric.to_csv(output_path, index=False, encoding="utf-8")
    return {"row_count": len(numeric), "headers": tuple(selected)}
```

Use `pandas.read_csv`, `pandas.ExcelFile` and `pandas.read_excel`; pass `engine="xlrd"` for `.xls` and `engine="openpyxl"` for `.xlsx`. Add exactly `pandas`, `xlrd`, and `xgboost` to `requirements.txt`.

- [ ] **Step 4: Run the data-contract tests**

Run: `pytest tests/test_custom_dataset.py -v`

Expected: PASS.

- [ ] **Step 5: Record the change**

Current checkout has no `.git`; do not run `git add` or `git commit`. Record that this step was skipped in the implementation handoff.

### Task 2: 自定义项目持久化与安全命令路由

**Files:**
- Modify: `src/platform/platform_core.py`
- Modify: `tests/test_platform_core.py`

**Interfaces:**
- Consumes `CustomDatasetConfig` and a canonical CSV written inside `project.path / "datasets"`.
- Produces `PlatformStore.create_custom_project(name: str, config: CustomDatasetConfig, trainer_script: Path) -> Project` and `build_custom_command(project: Project, settings: dict[str, object], python_executable: Path) -> tuple[list[str], Path]`.
- Custom project record adds a `custom_config` object but remains readable by `_project_from_record` as `Project`.

- [ ] **Step 1: Write failing persistence and command tests**

```python
def test_custom_project_persists_mapping_and_builds_fixed_command(tmp_path: Path) -> None:
    store = PlatformStore(tmp_path / "store")
    config = CustomDatasetConfig(tmp_path / "source.csv", None, "time", ("voltage", "current"), ("soc", "rul"), "gru")
    project = store.create_custom_project("我的电芯", config, PROJECT / "src/training/train_custom.py")

    command, run_dir = build_custom_command(project, {"window": 12, "epochs": 2, "seed": 7}, Path("/python"))

    assert project.name == "我的电芯"
    assert "-m" in command and "src.training.train_custom" in command
    assert command[command.index("--algorithm") + 1] == "gru"
    assert command[command.index("--targets") + 1:command.index("--targets") + 3] == ["soc", "rul"]
    assert run_dir.parent == project.path / "runs"
```

- [ ] **Step 2: Run the test to verify failure**

Run: `pytest tests/test_platform_core.py::PlatformStoreTests::test_custom_project_persists_mapping_and_builds_fixed_command -v`

Expected: FAIL because `create_custom_project` and `build_custom_command` are absent.

- [ ] **Step 3: Implement custom records and command construction**

```python
def create_custom_project(self, name: str, config: CustomDatasetConfig, trainer_script: Path) -> Project:
    project = self.create_project(name, str(trainer_script.resolve()), "")
    data_path = self.safe_child(project, "datasets/custom_training.csv")
    validate_and_export(config, data_path, minimum_rows=30)
    self._replace_record(project.project_id, data_path=str(data_path), custom_config=serialize_config(config))
    return self.get_project(project.project_id)

def build_custom_command(project: Project, settings: Dict[str, object], python_executable: Path) -> Tuple[List[str], Path]:
    config = custom_config_for(project)
    run_dir = create_run_dir(project)
    return [str(python_executable), "-m", "src.training.train_custom", "--data", str(project.data_path),
            "--results-dir", str(run_dir), "--algorithm", config["algorithm"],
            "--features", *config["feature_columns"], "--targets", *config["target_columns"],
            "--window", str(int(settings.get("window", 60))), "--epochs", str(int(settings.get("epochs", 40))),
            "--seed", str(int(settings.get("seed", 42)))], run_dir
```

Implement `_replace_record` with one read-modify-write of `projects.json`; on export failure remove the newly created project directory and registry record before re-raising. Never interpolate executable shell strings: commands remain argument lists.

- [ ] **Step 4: Run platform tests**

Run: `pytest tests/test_platform_core.py -v`

Expected: PASS, including existing project and deletion-safety tests.

- [ ] **Step 5: Record the change**

Skip the Git commit because no repository metadata exists.

### Task 3: 通用四算法训练器与统一结果工件

**Files:**
- Create: `src/training/train_custom.py`
- Create: `tests/test_train_custom.py`

**Interfaces:**
- Consumes canonical CSV and CLI values `--features`, `--targets`, `--algorithm`, `--window`, `--epochs`, `--batch-size`, `--hidden`, `--learning-rate`, `--seed`.
- Produces `run_training(...) -> dict[str, object]` plus the five global output files described above.
- Produces `SUPPORTED_ALGORITHMS = ("lstm", "gru", "xgboost", "transformer")` and rejects other names with `ValueError`.

- [ ] **Step 1: Write failing trainer tests**

```python
@pytest.mark.parametrize("algorithm", ["lstm", "gru", "xgboost", "transformer"])
def test_each_algorithm_writes_common_result_contract(tmp_path: Path, algorithm: str) -> None:
    data = write_small_numeric_csv(tmp_path / "cell.csv", rows=90)
    result = run_training(data, tmp_path / algorithm, features=("voltage", "current"), targets=("soc", "rul"),
                          algorithm=algorithm, window=5, epochs=1, batch_size=16, hidden=8, seed=42)

    assert result["metrics"]["n_test"] > 0
    assert set(json.loads((tmp_path / algorithm / "metrics_by_target.json").read_text())) == {"soc", "rul"}
    assert (tmp_path / algorithm / "test_predictions.csv").is_file()
    assert (tmp_path / algorithm / "run_config.json").is_file()

def test_unknown_custom_algorithm_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported algorithm"):
        run_training(tmp_path / "cell.csv", tmp_path / "run", features=("v",), targets=("soc",), algorithm="forest")
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_train_custom.py -v`

Expected: FAIL because `src.training.train_custom` does not exist.

- [ ] **Step 3: Implement leak-safe preparation and algorithm adapters**

```python
def run_training(data: Path, results_dir: Path, *, features: tuple[str, ...], targets: tuple[str, ...],
                 algorithm: str, window: int, epochs: int, batch_size: int, hidden: int, seed: int,
                 learning_rate: float = 3e-4) -> dict[str, object]:
    sequences, labels = _make_sequences(_read_numeric_csv(data, features, targets), features, targets, window)
    train, valid, test = _chronological_split(sequences, labels)
    scaler = _fit_scaler(train.features)
    predictor, history = _fit_algorithm(algorithm, train, valid, scaler, epochs, batch_size, hidden, learning_rate, seed)
    predictions = _predict(predictor, algorithm, test.features, scaler)
    return _write_results(results_dir, targets, test.labels, predictions, history, algorithm, features, window, seed)
```

Implement LSTM and GRU as a shared PyTorch recurrent regressor with a linear head sized to `len(targets)`. Implement Transformer with `nn.TransformerEncoder` and a final-token linear head. Implement XGBoost as `MultiOutputRegressor(XGBRegressor(n_estimators=max(20, epochs * 10), random_state=seed, n_jobs=1))` over flattened windows. Fit normalizers only on the chronological training split, never on validation/test. Print `epoch {number}` for each neural epoch so existing percentage progress works; XGBoost prints `epoch 1` before fit and `epoch {epochs}` after fit. Write target-wise MAE/RMSE and a top-level summary with `MAE`, `RMSE`, `n_train`, `n_validation`, `n_test`, `algorithm`, and `targets`.

- [ ] **Step 4: Run focused trainer tests**

Run: `pytest tests/test_train_custom.py -v`

Expected: PASS; use the smallest one-epoch data fixture to keep execution bounded.

- [ ] **Step 5: Record the change**

Skip the Git commit because no repository metadata exists.

### Task 4: 桌面导入向导、算法建议与自定义训练/结果界面

**Files:**
- Modify: `src/desktop/app.py`
- Modify: `tests/test_desktop_app.py`

**Interfaces:**
- Consumes `list_sheet_names`, `read_headers`, `CustomDatasetConfig`, `PlatformStore.create_custom_project`, and `build_custom_command`.
- Produces `DesktopTrainingApp.open_custom_dataset_dialog() -> None`, `_recommended_algorithm(targets: tuple[str, ...]) -> str`, and custom-project branch in `start_training`.

- [ ] **Step 1: Write failing desktop contract tests**

```python
def test_custom_target_algorithm_recommendations_are_predictable() -> None:
    assert DesktopTrainingApp._recommended_algorithm(("soc",)) == "lstm"
    assert DesktopTrainingApp._recommended_algorithm(("SOE", "sot")) == "lstm"
    assert DesktopTrainingApp._recommended_algorithm(("rul_cycles",)) == "xgboost"

def test_desktop_source_exposes_custom_import_and_command_route() -> None:
    source = (PROJECT / "src/desktop/app.py").read_text(encoding="utf-8")
    assert "自定义数据集…" in source
    assert "filedialog.askopenfilename" in source
    assert "build_custom_command" in source
    assert "LSTM" in source and "GRU" in source and "XGBoost" in source and "Transformer" in source
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `pytest tests/test_desktop_app.py::DesktopTrainingAppTests::test_custom_target_algorithm_recommendations_are_predictable tests/test_desktop_app.py::DesktopTrainingAppTests::test_desktop_source_exposes_custom_import_and_command_route -v`

Expected: FAIL because the new dialog and router do not exist.

- [ ] **Step 3: Implement the minimal Tkinter flow**

```python
def _recommended_algorithm(targets: tuple[str, ...]) -> str:
    normalized = {target.strip().lower() for target in targets}
    return "xgboost" if normalized and all("rul" in target for target in normalized) else "lstm"

def open_custom_dataset_dialog(self) -> None:
    source = Path(filedialog.askopenfilename(filetypes=[("数据文件", "*.csv *.xlsx *.xls")]))
    if not source.name:
        return
    # Toplevel: project name, optional sheet selector, time selector, multi-select feature/target listboxes,
    # readable algorithm combobox, recommendation label, and a "导入并创建项目" button.
```

Add “自定义数据集…” as the final combobox option, and handle it separately so it cannot become `self.project`. After a valid import, reload `store.list_projects()`, set the newly created project, refresh combobox values, and navigate to the dataset summary. Populate algorithm labels as `LSTM`, `GRU`, `XGBoost`, `Transformer` but store their lowercase IDs. For a custom project, render its selected algorithm/feature/target summary in `show_dataset`; show a simplified common settings form in `show_training`; route `start_training` to `build_custom_command`; and show target-wise metrics plus a generic “预测对比” tab in `show_results`. Keep all existing NASA/A123 branches unchanged.

- [ ] **Step 4: Run desktop and route tests**

Run: `pytest tests/test_desktop_app.py tests/test_platform_core.py -v`

Expected: PASS; Tk tests may be skipped only when the environment has no display.

- [ ] **Step 5: Record the change**

Skip the Git commit because no repository metadata exists.

### Task 5: 全量回归与可运行性验证

**Files:**
- Modify only if a failing test exposes a direct regression in the files above.

**Interfaces:**
- Consumes all completed task interfaces.
- Produces evidence that custom and legacy workflows coexist.

- [ ] **Step 1: Run custom feature suite**

Run: `pytest tests/test_custom_dataset.py tests/test_train_custom.py tests/test_platform_core.py tests/test_desktop_app.py -v`

Expected: PASS, with display-dependent desktop tests reported as skipped rather than failed.

- [ ] **Step 2: Run the complete repository suite**

Run: `pytest -v`

Expected: PASS or only pre-existing environment skips. Investigate any new failure before reporting completion.

- [ ] **Step 3: Exercise a headless import-to-command smoke path**

Run: `python -c 'from pathlib import Path; from src.custom_training.dataset import CustomDatasetConfig, validate_and_export; print("custom import API available")'`

Expected: prints `custom import API available` and exits 0.

- [ ] **Step 4: Record verification and change status**

Report the exact test command results. Do not claim successful completion without those results. Skip Git commit because no repository metadata exists.
