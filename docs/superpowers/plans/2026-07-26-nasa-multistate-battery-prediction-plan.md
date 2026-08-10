# NASA 多状态电池预测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有 A123#3 SOC 任务的情况下，基于 NASA PCoE 老化数据建立可追溯的 SOC、SOH、SOE、RUL、SOT 五目标训练、评估和平台展示流程。

**Architecture:** 原始 NASA 压缩包下载到数据中心，解析器将 MATLAB 循环记录转换为长表并按电芯进行独立训练/验证/测试划分。多状态 LSTM 使用共享时间序列编码器与五个回归头；训练工件以独立实验目录保存，再由平台作为第二个内置项目读取。

**Tech Stack:** Python 3.12、PyTorch、NumPy、SciPy（MATLAB v5 `.mat` 解析）、Tkinter、Pillow、unittest。

## Global Constraints

- 原始数据、派生训练数据、审计报告与实验结果都存放在 `E:\SOC电池数据中心`，不得覆盖 A123#3 数据或结果。
- 数据源固定为 NASA PCoE Battery Data Set：`https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip`；下载后必须记录 SHA-256、来源 URL 与下载日期。
- SOC、SOH、SOE、RUL、SOT 的定义必须与设计文档一致，缺失或不可计算标签不得伪造。
- 训练/验证/测试必须以 `cell_id` 独立划分；窗口不得跨电芯或循环；标准化只能从训练电芯获得。
- SOT 是数据集中实测电芯温度的状态代理，不宣称为内部三维温度场。
- 旧的 `src.training.train_lstm`、`A123 SOC` 项目和旧实验目录保持兼容。

---

## File Structure

- Create `src/data_processing/download_nasa_aging.py`：可恢复下载、SHA-256 记录和安全解压。
- Create `src/data_processing/prepare_nasa_multistate.py`：MATLAB 循环解析、标签计算、数据审计与按电芯划分。
- Create `src/training/train_multistate_lstm.py`：共享 LSTM + 五头回归、训练、测试工件与五目标指标。
- Create `src/evaluation/analyze_multistate_predictions.py`：按目标输出 MAE、RMSE 和可审计预测表检查。
- Create `src/desktop/multistate_charts.py`：五个目标的独立 PNG/SVG 曲线生成。
- Modify `src/project_paths.py`：增加 NASA 原始、训练、结果和运行目录属性。
- Modify `src/platform/platform_core.py`：注册第二个内置项目 `NASA 五状态`，识别多状态完整结果。
- Modify `src/desktop/app.py`：项目概览、训练入口和结果页按项目类型选择 SOC 或多状态工件。
- Create `tests/test_download_nasa_aging.py`、`tests/test_prepare_nasa_multistate.py`、`tests/test_train_multistate_lstm.py`、`tests/test_analyze_multistate_predictions.py`、`tests/test_multistate_charts.py`；扩展 `tests/test_project_paths.py`、`tests/test_platform_core.py`、`tests/test_desktop_app.py`。
- Create `E:\SOC电池数据中心\01_原始数据\03_NASA_PCoE_多状态原始数据\`、`02_训练数据\02_NASA_五状态训练数据\`、`03_模型与实验结果\04_NASA_五状态模型与结果\`、`04_训练平台运行记录\02_NASA_五状态训练平台记录\`（仅由已验证脚本创建）。

### Task 1: 数据中心路径与下载器

**Files:**
- Modify: `src/project_paths.py`
- Create: `src/data_processing/download_nasa_aging.py`
- Create: `tests/test_project_paths.py` additions
- Create: `tests/test_download_nasa_aging.py`

**Interfaces:**
- Produces `DataCenterPaths.nasa_raw_dir`, `nasa_training_dir`, `nasa_results_dir`, `nasa_runs_dir` (`Path`)。
- Produces `download_and_extract(url: str, archive_path: Path, extract_dir: Path) -> dict[str, str]`，返回 `source_url`、`sha256`、`archive_path`、`extract_dir`。

- [ ] **Step 1: 写出会失败的路径测试**

```python
def test_nasa_multistate_paths_are_isolated(tmp_path):
    paths = DataCenterPaths(tmp_path)
    assert paths.nasa_raw_dir == tmp_path / "01_原始数据" / "03_NASA_PCoE_多状态原始数据"
    assert paths.nasa_training_dir != paths.training_csv.parent
    assert paths.nasa_results_dir != paths.baseline_results_dir
```

- [ ] **Step 2: 运行路径测试并确认失败**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_project_paths -v`

Expected: `AttributeError: 'DataCenterPaths' object has no attribute 'nasa_raw_dir'`。

- [ ] **Step 3: 增加四个只读路径属性**

```python
@property
def nasa_training_dir(self) -> Path:
    return self.root / "02_训练数据" / "02_NASA_五状态训练数据"
```

按相同模式实现其余三个路径，目录名使用 File Structure 中的固定名称。

- [ ] **Step 4: 写出下载器测试**

```python
def test_download_rejects_zip_path_escape(tmp_path):
    archive = tmp_path / "bad.zip"
    _zip(archive, {"../outside.txt": b"x"})
    with self.assertRaisesRegex(ValueError, "escapes extraction directory"):
        extract_verified_zip(archive, tmp_path / "out")
```

- [ ] **Step 5: 实现最小安全下载器**

```python
NASA_URL = "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

使用 `urllib.request.urlretrieve` 写到 `archive_path.with_suffix('.part')`，下载完成后原子替换；逐个检查 ZIP 成员 `resolve()` 后仍位于目标目录内；写入 `download_manifest.json`。若压缩包已经存在且清单哈希一致，不重复下载。

- [ ] **Step 6: 运行下载器与路径测试**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_project_paths tests.test_download_nasa_aging -v`

Expected: PASS。

### Task 2: NASA 解析、标签和审计

**Files:**
- Create: `src/data_processing/prepare_nasa_multistate.py`
- Create: `tests/test_prepare_nasa_multistate.py`

**Interfaces:**
- Consumes解压后的 `B0005.mat`、`B0006.mat`、`B0007.mat`、`B0018.mat`。
- Produces `prepare_multistate_dataset(raw_dir: Path, output_dir: Path, eol_soh: float = 0.70) -> dict[str, object]`。
- 输出 `nasa_multistate_samples.csv`、`data_audit.json`、`data_dictionary.json`、`split_manifest.json`。

- [ ] **Step 1: 写出最小循环标签测试**

```python
def test_discharge_labels_are_traceable():
    row = derive_cycle_labels(capacity_ah=1.8, initial_capacity_ah=2.0,
                              remaining_energy_wh=2.7, initial_energy_wh=3.0,
                              cycle_index=10, eol_cycle_index=50)
    self.assertAlmostEqual(row["soh"], 0.9)
    self.assertAlmostEqual(row["soe"], 0.9)
    self.assertEqual(row["rul_cycles"], 40)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_prepare_nasa_multistate -v`

Expected: import error because module does not yet exist。

- [ ] **Step 3: 实现循环解析和五种标签**

```python
TARGET_COLUMNS = ("soc", "soh", "soe", "rul_cycles", "sot_c")

def derive_cycle_labels(*, capacity_ah, initial_capacity_ah,
                        remaining_energy_wh, initial_energy_wh,
                        cycle_index, eol_cycle_index):
    return {
        "soh": capacity_ah / initial_capacity_ah,
        "soe": remaining_energy_wh / initial_energy_wh,
        "rul_cycles": eol_cycle_index - cycle_index,
    }
```

使用 `scipy.io.loadmat(..., squeeze_me=True, struct_as_record=False)` 读取 MATLAB 结构。仅采用有 `Capacity`、`Voltage_measured`、`Current_measured`、`Temperature_measured`、`Time` 的放电循环。SOH 用每个电芯第一个有效放电循环容量归一化；EOL 为 SOH 首次 `<= 0.70` 的循环；RUL 为该 EOL 循环号减当前循环号；没有达到 EOL 的电芯从数据集排除。SOC 根据放电累计绝对 Ah 从 1 递减至 0；SOE 为从当前样本到本循环结束的 `sum(abs(V*I)*dt)` 除以该电芯第一有效循环能量；SOT 为 `Temperature_measured`。

- [ ] **Step 4: 实现防泄漏的电芯划分与审计**

```python
def fixed_cell_split(cell_ids: list[str]) -> dict[str, list[str]]:
    required = ["B0005", "B0006", "B0007", "B0018"]
    if sorted(cell_ids) != required:
        raise ValueError("Expected exactly NASA cells B0005, B0006, B0007, B0018")
    return {"train": ["B0005", "B0006"], "validation": ["B0007"], "test": ["B0018"]}
```

审计必须包含每个目标、每个 split 的非空计数，原始文件名、SHA-256、每个电芯初始容量、EOL 循环、排除原因和标签版本；若任意目标或 split 计数为零，抛出 `ValueError` 并不创建可训练标记文件。

- [ ] **Step 5: 运行预处理测试**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_prepare_nasa_multistate -v`

Expected: PASS，包括跨电芯划分、EOL 缺失拒绝、窗口标签完整性。

### Task 3: 五目标训练器与评估

**Files:**
- Create: `src/training/train_multistate_lstm.py`
- Create: `src/evaluation/analyze_multistate_predictions.py`
- Create: `tests/test_train_multistate_lstm.py`
- Create: `tests/test_analyze_multistate_predictions.py`

**Interfaces:**
- `MultiStateLSTM(n_features: int, hidden: int, dropout: float)` 返回 `dict[str, Tensor]`，键为 `soc`、`soh`、`soe`、`rul_cycles`、`sot_c`。
- `make_multistate_sequences(rows: np.ndarray, feature_mean: np.ndarray, feature_std: np.ndarray, target_mean: np.ndarray, target_std: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]`。
- CLI: `python -m src.training.train_multistate_lstm --data <csv> --results-dir <dir> --window 60 --epochs 40`。

- [ ] **Step 1: 写出会失败的输出形状测试**

```python
def test_multistate_model_returns_all_five_targets():
    model = MultiStateLSTM(n_features=4, hidden=8, dropout=0.0)
    output = model(torch.zeros(3, 6, 4))
    self.assertEqual(set(output), {"soc", "soh", "soe", "rul_cycles", "sot_c"})
    self.assertEqual(output["rul_cycles"].shape, (3,))
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_train_multistate_lstm -v`

Expected: import error because module does not yet exist。

- [ ] **Step 3: 实现共享 LSTM 和掩码 Huber 损失**

```python
TARGETS = ("soc", "soh", "soe", "rul_cycles", "sot_c")

class MultiStateLSTM(nn.Module):
    def __init__(self, n_features, hidden=32, dropout=0.10):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.heads = nn.ModuleDict({name: nn.Sequential(nn.Linear(hidden, 16), nn.ReLU(), nn.Dropout(dropout), nn.Linear(16, 1)) for name in TARGETS})
```

对每个可用目标使用标准化 `HuberLoss`；将每目标平均损失相加后除以可用目标数。使用训练电芯计算特征和目标标准化参数。每个训练窗口仅来自同一 `cell_id` 与 `cycle_id`。

- [ ] **Step 4: 输出可审计实验工件**

保存 `multistate_lstm.pt`、`metrics.json`、`metrics_by_target.json`、`training_history.json`、`run_config.json`、`test_predictions.csv`。`metrics_by_target.json` 每个目标必须含原始单位 MAE、RMSE、`n_test`；`run_config.json` 写入 `split_manifest` 的路径与哈希。训练期间每 epoch 输出 `PROGRESS: <percent>`，供现有桌面进度条复用。

- [ ] **Step 5: 实现并测试评估器**

```python
def summarize_target_errors(rows, target: str) -> dict[str, float | int]:
    error = np.asarray(rows[f"predicted_{target}"]) - np.asarray(rows[f"reference_{target}"])
    return {"MAE": float(np.mean(np.abs(error))), "RMSE": float(np.sqrt(np.mean(error ** 2))), "n": int(error.size)}
```

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_train_multistate_lstm tests.test_analyze_multistate_predictions -v`

Expected: PASS，且测试断言 RUL 使用循环数、温度使用摄氏度，SOC/SOH/SOE 为归一化值。

### Task 4: 图表和训练平台兼容

**Files:**
- Create: `src/desktop/multistate_charts.py`
- Modify: `src/platform/platform_core.py`
- Modify: `src/desktop/app.py`
- Create: `tests/test_multistate_charts.py`
- Modify: `tests/test_platform_core.py`
- Modify: `tests/test_desktop_app.py`

**Interfaces:**
- `build_multistate_charts(run_dir: Path) -> dict[str, Path]` 返回五个 PNG 图路径。
- `PlatformStore.ensure_nasa_multistate_project(trainer_script: Path, data_path: Path) -> Project`。
- `latest_complete_run_result(...)` 必须同时支持旧 SOC 工件及含 `metrics_by_target.json` 的多状态工件。

- [ ] **Step 1: 写出图表和项目注册失败测试**

```python
def test_store_creates_second_builtin_project(tmp_path):
    store = PlatformStore(tmp_path)
    project = store.ensure_nasa_multistate_project(Path("trainer.py"), Path("data.csv"))
    self.assertEqual(project.name, "NASA 五状态")
```

- [ ] **Step 2: 实现五目标图表**

每张图读取 `test_predictions.csv` 的 `reference_<target>` 与 `predicted_<target>` 列，生成标题、单位和 MAE/RMSE。SOC、SOH、SOE 标注为 `%`；RUL 标注为 `cycles`；SOT 标注为 `°C`。没有完整列时抛出明确异常。

- [ ] **Step 3: 注册第二个内置项目并保留旧项目**

```python
def ensure_nasa_multistate_project(self, trainer_script: Path, data_path: Path) -> Project:
    return self._ensure_named_project("NASA 五状态", trainer_script, data_path)
```

提取 `ensure_soc_project` 的共同逻辑为私有 `_ensure_named_project`，保持名称 `A123 SOC` 和原记录结构不变。多状态项目只能指向 `train_multistate_lstm.py` 及 NASA 训练 CSV。

- [ ] **Step 4: 修改桌面显示与训练启动**

当选择项目名为 `NASA 五状态` 时，显示训练数据状态、五个目标的最新指标和五张结果图；训练命令调用新模块。缺数据、未完成数据审计或五目标工件不齐时禁用“开始训练”，显示具体缺失文件。所有现有 SOC 页面维持原文本、图表和删除机制。

- [ ] **Step 5: 运行平台测试**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_multistate_charts tests.test_platform_core tests.test_desktop_app -v`

Expected: PASS，包含 SOC 旧项目和 NASA 五状态项目共存。

### Task 5: 受控下载、数据构建与小规模端到端验证

**Files:**
- Generated only under the four NASA data-center directories defined above。
- Modify: `README.md`
- Create: `docs/NASA五状态数据与训练说明.md`

**Interfaces:**
- 依赖 Tasks 1–4 通过。
- 产生 `data_audit.json`，并作为训练前置条件。

- [ ] **Step 1: 检查磁盘空间与下载目录**

Run: `Get-PSDrive E | Select-Object Used,Free` and confirm `E:` has at least 6 GB free before download. Create only the NASA directories from File Structure.

- [ ] **Step 2: 下载并验证原始数据**

Run: `..\..\work\soc_venv\Scripts\python.exe -m src.data_processing.download_nasa_aging --data-root "E:\SOC电池数据中心"`

Expected: `download_manifest.json` exists, SHA-256 is 64 hexadecimal characters, and extracted `B0005.mat`/`B0006.mat`/`B0007.mat`/`B0018.mat` exist.

- [ ] **Step 3: 生成标签、清单和审计报告**

Run: `..\..\work\soc_venv\Scripts\python.exe -m src.data_processing.prepare_nasa_multistate --data-root "E:\SOC电池数据中心"`

Expected: `data_audit.json` reports nonzero five-target counts for train, validation and test, with no overlapping `cell_id` values.

- [ ] **Step 4: 运行小规模端到端烟雾训练**

Run: `..\..\work\soc_venv\Scripts\python.exe -m src.training.train_multistate_lstm --data "E:\SOC电池数据中心\02_训练数据\02_NASA_五状态训练数据\nasa_multistate_samples.csv" --results-dir "E:\SOC电池数据中心\03_模型与实验结果\04_NASA_五状态模型与结果\smoke" --epochs 2 --max-train 512 --max-valid 256 --max-test 256`

Expected: five-target metrics, prediction CSV and five chart inputs; no error and no A123 file modified.

- [ ] **Step 5: 运行完整回归测试**

Run: `..\..\work\soc_venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS; if the pre-existing IDE-layout test still requires removed `.idea/workspace.xml`, record it separately rather than changing unrelated layout logic.

### Task 6: 正式训练、结果验收与用户交付

**Files:**
- Generated: `E:\SOC电池数据中心\03_模型与实验结果\04_NASA_五状态模型与结果\<run-id>\`
- Generated: `E:\SOC电池数据中心\04_训练平台运行记录\02_NASA_五状态训练平台记录\`
- Modify: `docs/NASA五状态数据与训练说明.md`

**Interfaces:**
- 依赖通过的 smoke training 和完整测试。
- 生成可由桌面平台读取的完整 run 目录。

- [ ] **Step 1: 在平台中选中 `NASA 五状态` 并确认数据审计为通过状态**

Expected: 训练按钮可用，状态页列出五个目标、来源、电芯划分和训练目录。

- [ ] **Step 2: 运行正式 CPU 训练**

使用平台默认配置启动；每个 epoch 必须输出 `PROGRESS:`，平台显示常驻动态进度条。训练结果写入新的时间戳目录，不复用 smoke 目录。

- [ ] **Step 3: 检查交付工件**

验证以下文件存在且非空：`multistate_lstm.pt`、`metrics.json`、`metrics_by_target.json`、`test_predictions.csv`、`training_history.json`、`run_config.json`、五张预测图、`run.log`。验证 `test_predictions.csv` 包含十列 `reference_*`/`predicted_*`。

- [ ] **Step 4: 更新教学说明**

说明数据来源、五类标签公式与单位、独立电芯划分、模型输入/输出、如何从平台启动训练、如何读取每个目标的 MAE/RMSE，以及 SOT 代理定义的限制。

- [ ] **Step 5: 最终复核**

再次运行核心单元测试与解析脚本的审计检查；报告实际样本数、训练电芯、验证电芯、测试电芯、五个测试指标、模型与数据的绝对路径，且明确指标只代表 NASA 数据集上的独立电芯测试。

## Self-Review

- Spec coverage: Task 1 覆盖独立目录与可验证下载；Task 2 覆盖五标签和独立电芯划分；Task 3 覆盖共享五头模型及指标；Task 4 覆盖平台；Tasks 5–6 覆盖实际下载、训练、审计与教学交付。
- Placeholder scan: 未发现占位符或延后实现描述；每个任务包含具体文件、接口、测试与命令。
- Type consistency: `TARGETS` 的五个键在数据、模型、预测 CSV、评估及图表任务中一致；RUL 键固定为 `rul_cycles`，SOT 键固定为 `sot_c`。
