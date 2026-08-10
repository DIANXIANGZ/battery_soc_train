# SOC Research Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立跨数据集 SOC 科研流程的可信基础，包括冻结协议、统一数据契约、资产清单、质量审计、双标签、泄漏检测、域分割和合成数据端到端验证。

**Architecture:** 在新的 `src/research` 包中实现相互独立的纯 Python 组件，由 `pipeline.py` 组合；现有 `src/training`、`src/evaluation` 和桌面平台保持不变。第一周期只处理研究基础与审计，不训练新的正式模型，也不改写原始数据或历史基线。

**Tech Stack:** Python 3.12、标准库 `dataclasses/csv/json/hashlib/statistics/pathlib`、现有 `unittest` 测试体系、JSON 配置与 Markdown 报告。

## Global Constraints

- 第一版仅研究同一化学体系内的跨数据集、跨电芯、跨温度、跨工况和跨老化泛化。
- `E:\SOC电池数据中心\01_原始数据`、现有 A123#3/A123#5 结果和正式泛化目录只读使用。
- 新产物只写入 `research_v1` 或测试临时目录，拒绝覆盖非空目录。
- 训练、验证和测试不得共享 `dataset_id + cell_id`；窗口不得跨数据集、电芯、会话或循环。
- 归一化和特征统计只能由训练域拟合。
- 第一周期不增加第三方依赖，不训练正式模型，不下载外部数据。
- 每个新增行为必须先观察目标测试因行为缺失而失败，再写最少生产代码。
- 当前 shell 找不到 `git`；计划仍列出精确提交命令，实际提交必须等 Git 可用后执行，不能伪造提交结果。

## File Map

- `src/research/protocol.py`：读取并验证冻结科研协议。
- `src/research/schema.py`：统一样本数据契约和单位范围验证。
- `src/research/manifest.py`：只读扫描文件并计算流式 SHA-256。
- `src/research/quality.py`：对统一样本执行高信号质量统计。
- `src/research/labels.py`：生成离线循环范围标签和在线历史可用标签。
- `src/research/leakage.py`：检查域重叠、窗口跨界和统计污染。
- `src/research/splits.py`：生成留一数据集和留一电芯折叠。
- `src/research/pipeline.py`：编排第一周期审计并原子写入产物。
- `configs/research/protocol_v1.json`：冻结第一版范围、角色、种子和门槛状态。
- `configs/research/datasets.json`：登记 A123#3、A123#5、CX2_4 的研究角色。
- `tests/research/`：对应模块测试及合成数据端到端测试。

---

### Task 1: 冻结科研协议与数据集登记

**Files:**
- Create: `src/research/__init__.py`
- Create: `src/research/protocol.py`
- Create: `configs/research/protocol_v1.json`
- Create: `configs/research/datasets.json`
- Test: `tests/research/__init__.py`
- Test: `tests/research/test_protocol.py`

**Interfaces:**
- Produces: `ResearchProtocol`, `DatasetRegistration`, `load_protocol(path: Path) -> ResearchProtocol`, `load_dataset_registry(path: Path) -> tuple[DatasetRegistration, ...]`.
- Consumes: no new project interfaces.

- [ ] **Step 1: Write the failing protocol tests**

```python
def test_protocol_loads_frozen_scope_and_unique_seeds(self):
    protocol = load_protocol(self.protocol_path)
    self.assertEqual("same_chemistry_cross_dataset", protocol.scope)
    self.assertEqual((11, 23, 42, 67, 101), protocol.seeds)
    self.assertTrue(protocol.external_test_locked)

def test_protocol_rejects_duplicate_seeds_and_unlocked_external_test(self):
    payload = self.valid_payload | {"seeds": [11, 11], "external_test_locked": False}
    with self.assertRaisesRegex(ValueError, "unique.*external"):
        load_protocol(self.write_json(payload))

def test_dataset_registry_assigns_each_dataset_one_role(self):
    records = load_dataset_registry(self.registry_path)
    self.assertEqual({"A123#3", "A123#5", "CX2_4"}, {item.dataset_id for item in records})
    self.assertEqual("compatibility_audit", next(x.role for x in records if x.dataset_id == "CX2_4"))
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m unittest tests.research.test_protocol -v`  
Expected: `ModuleNotFoundError: No module named 'src.research'`.

- [ ] **Step 3: Implement immutable protocol types and strict JSON validation**

```python
@dataclass(frozen=True)
class ResearchProtocol:
    version: str
    scope: str
    seeds: tuple[int, ...]
    external_test_locked: bool
    minimum_primary_datasets: int

@dataclass(frozen=True)
class DatasetRegistration:
    dataset_id: str
    chemistry: str
    role: str
    source_root: Path
    label_method: str

def load_protocol(path: Path) -> ResearchProtocol:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    seeds = tuple(int(value) for value in payload["seeds"])
    errors = []
    if len(seeds) != len(set(seeds)):
        errors.append("seeds must be unique")
    if payload.get("external_test_locked") is not True:
        errors.append("external test must be locked")
    if errors:
        raise ValueError("; ".join(errors))
    return ResearchProtocol(
        version=str(payload["version"]),
        scope=str(payload["scope"]),
        seeds=seeds,
        external_test_locked=True,
        minimum_primary_datasets=int(payload["minimum_primary_datasets"]),
    )
```

`protocol_v1.json` 固定 `version=research_v1`、`scope=same_chemistry_cross_dataset`、五个既有随机种子、`external_test_locked=true`、`minimum_primary_datasets=3`。`datasets.json` 将 A123#3 登记为开发域、A123#5 登记为冻结外部域、CX2_4 登记为兼容性审计域，不把 CX2_4 混入 A123 主实验。

- [ ] **Step 4: Run the task tests and full protocol regression**

Run: `python -m unittest tests.research.test_protocol -v`  
Expected: all protocol tests pass.

- [ ] **Step 5: Commit when Git is available**

```powershell
git add src/research/__init__.py src/research/protocol.py configs/research tests/research/__init__.py tests/research/test_protocol.py
git commit -m "feat: freeze SOC research protocol"
```

---

### Task 2: 建立统一样本数据契约

**Files:**
- Create: `src/research/schema.py`
- Test: `tests/research/test_schema.py`

**Interfaces:**
- Produces: `SampleRecord`, `SampleKey`, `validate_record(record: SampleRecord) -> tuple[str, ...]`, `parse_record(mapping: Mapping[str, object]) -> SampleRecord`.
- Consumes: dataset identifiers defined by Task 1.

- [ ] **Step 1: Write failing schema tests**

```python
def test_valid_record_preserves_traceability_key(self):
    record = parse_record(self.valid_mapping)
    self.assertEqual(SampleKey("A123#3", "cell-3", "run-1", "cycle-7", 30.0), record.key)
    self.assertEqual((), validate_record(record))

def test_invalid_voltage_soc_and_identity_are_all_reported(self):
    bad = self.valid_mapping | {"cell_id": "", "voltage_v": 9.0, "soc_reference": 1.2}
    errors = validate_record(parse_record(bad))
    self.assertTrue(any("cell_id" in item for item in errors))
    self.assertTrue(any("voltage_v" in item for item in errors))
    self.assertTrue(any("soc_reference" in item for item in errors))
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.research.test_schema -v`  
Expected: import failure for `src.research.schema`.

- [ ] **Step 3: Implement typed schema and explicit ranges**

```python
@dataclass(frozen=True)
class SampleKey:
    dataset_id: str
    cell_id: str
    session_id: str
    cycle_id: str
    timestamp_s: float

@dataclass(frozen=True)
class SampleRecord:
    key: SampleKey
    voltage_v: float
    current_a: float
    temperature_c: float | None
    capacity_ah: float | None
    soh: float | None
    soc_reference: float | None
    label_method: str
    split_role: str
    source_file: str

def validate_record(record: SampleRecord) -> tuple[str, ...]:
    errors = []
    for name, value in (("dataset_id", record.key.dataset_id), ("cell_id", record.key.cell_id),
                        ("session_id", record.key.session_id), ("cycle_id", record.key.cycle_id),
                        ("source_file", record.source_file)):
        if not value.strip():
            errors.append(f"{name} must be non-empty")
    if not 0.0 < record.voltage_v <= 6.0:
        errors.append("voltage_v must be in (0, 6]")
    if record.soc_reference is not None and not 0.0 <= record.soc_reference <= 1.0:
        errors.append("soc_reference must be in [0, 1]")
    if record.soh is not None and not 0.0 < record.soh <= 2.0:
        errors.append("soh must be in (0, 2]")
    return tuple(errors)
```

`parse_record` 对必需字段缺失给出字段名明确的 `ValueError`，将空温度、容量、SOH 和 SOC 解析为 `None`，不静默填充为零。

- [ ] **Step 4: Verify GREEN and relevant regressions**

Run: `python -m unittest tests.research.test_schema tests.test_code_layout -v`  
Expected: all selected tests pass.

- [ ] **Step 5: Commit when Git is available**

```powershell
git add src/research/schema.py tests/research/test_schema.py
git commit -m "feat: add research sample schema"
```

---

### Task 3: 创建只读资产清单和基线哈希

**Files:**
- Create: `src/research/manifest.py`
- Test: `tests/research/test_manifest.py`

**Interfaces:**
- Produces: `FileAsset`, `sha256_file(path: Path) -> str`, `scan_assets(dataset: DatasetRegistration) -> tuple[FileAsset, ...]`, `write_manifest(path: Path, assets: Sequence[FileAsset]) -> None`.
- Consumes: `DatasetRegistration` from Task 1.

- [ ] **Step 1: Write failing manifest tests**

```python
def test_scan_is_deterministic_and_hashes_file_contents(self):
    assets = scan_assets(self.registration)
    self.assertEqual(["a.csv", "nested/b.xlsx"], [item.relative_path for item in assets])
    self.assertEqual(hashlib.sha256(b"alpha").hexdigest(), assets[0].sha256)

def test_manifest_refuses_to_overwrite_existing_output(self):
    output = self.root / "manifest.json"
    output.write_text("user data", encoding="utf-8")
    with self.assertRaises(FileExistsError):
        write_manifest(output, ())
    self.assertEqual("user data", output.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.research.test_manifest -v`  
Expected: import failure for `src.research.manifest`.

- [ ] **Step 3: Implement streaming hashes and deterministic scanning**

```python
@dataclass(frozen=True)
class FileAsset:
    dataset_id: str
    relative_path: str
    size_bytes: int
    sha256: str
    extension: str

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def scan_assets(dataset: DatasetRegistration) -> tuple[FileAsset, ...]:
    root = dataset.source_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(root).as_posix())
    return tuple(FileAsset(dataset.dataset_id, path.relative_to(root).as_posix(),
                           path.stat().st_size, sha256_file(path), path.suffix.lower()) for path in files)
```

`write_manifest` 使用临时文件加 `Path.replace` 原子写入，但在目标存在时直接抛出 `FileExistsError`。

- [ ] **Step 4: Verify GREEN and baseline hash compatibility**

Run: `python -m unittest tests.research.test_manifest tests.test_generalization_experiments.GeneralizationExperimentTests.test_sha256_files_detects_a_changed_baseline -v`  
Expected: all selected tests pass.

- [ ] **Step 5: Commit when Git is available**

```powershell
git add src/research/manifest.py tests/research/test_manifest.py
git commit -m "feat: add immutable research asset manifests"
```

---

### Task 4: 实现数据质量剖面与兼容性判断

**Files:**
- Create: `src/research/quality.py`
- Test: `tests/research/test_quality.py`

**Interfaces:**
- Produces: `QualityReport`, `profile_records(records: Iterable[SampleRecord]) -> QualityReport`, `assess_compatibility(registration: DatasetRegistration, report: QualityReport, target_chemistry: str) -> str`.
- Consumes: Task 1 registration and Task 2 records.

- [ ] **Step 1: Write failing quality tests**

```python
def test_profile_reports_rates_duplicates_time_reversal_and_coverage(self):
    report = profile_records(self.records_with_known_issues)
    self.assertEqual(4, report.row_count)
    self.assertEqual(0.25, report.missing_temperature_rate)
    self.assertEqual(1, report.duplicate_key_count)
    self.assertEqual(1, report.time_reversal_count)
    self.assertEqual(("A123#3",), report.dataset_ids)

def test_other_chemistry_is_compatibility_only(self):
    status = assess_compatibility(self.cx2, self.clean_report, target_chemistry="LFP")
    self.assertEqual("compatibility_only_chemistry_mismatch", status)
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.research.test_quality -v`  
Expected: import failure for `src.research.quality`.

- [ ] **Step 3: Implement compact rates and domain coverage**

`QualityReport` 保存总行数、无效行数、重复键数、时间逆序数、温度/容量/SOH/SOC 缺失率、各数据集/电芯/会话/循环数量、数值最小最大值和问题列表。所有缺失统计使用比例；空输入直接抛出 `ValueError("quality profile requires at least one record")`。

```python
def _rate(count: int, total: int) -> float:
    return count / total

def assess_compatibility(registration, report, target_chemistry):
    if registration.chemistry != target_chemistry:
        return "compatibility_only_chemistry_mismatch"
    if not report.has_soc_reference:
        return "compatibility_only_missing_soc_label"
    if report.distinct_cell_count < 1:
        return "rejected_missing_cell_identity"
    return "eligible_pending_split_review"
```

- [ ] **Step 4: Verify GREEN**

Run: `python -m unittest tests.research.test_quality tests.research.test_schema -v`  
Expected: all selected tests pass.

- [ ] **Step 5: Commit when Git is available**

```powershell
git add src/research/quality.py tests/research/test_quality.py
git commit -m "feat: profile SOC dataset quality"
```

---

### Task 5: 实现离线与在线 SOC 标签

**Files:**
- Create: `src/research/labels.py`
- Test: `tests/research/test_labels.py`

**Interfaces:**
- Produces: `LabelledPoint`, `offline_cycle_range_labels(points: Sequence[CapacityPoint]) -> tuple[LabelledPoint, ...]`, `online_coulomb_labels(points: Sequence[CurrentPoint], initial_soc: float, reference_capacity_ah: float) -> tuple[LabelledPoint, ...]`.
- Consumes: ordered points within one dataset/cell/session/cycle boundary.

- [ ] **Step 1: Write failing label tests**

```python
def test_offline_cycle_range_matches_legacy_reference_definition(self):
    labels = offline_cycle_range_labels(self.capacity_points([0.0, 0.5, 1.0]))
    self.assertEqual([0.0, 0.5, 1.0], [item.soc for item in labels])
    self.assertTrue(all(item.label_method == "offline_cycle_range" for item in labels))

def test_online_labels_use_only_past_current_and_fixed_capacity(self):
    points = self.current_points(times=[0, 3600, 7200], currents=[0, 1, 1])
    labels = online_coulomb_labels(points, initial_soc=0.2, reference_capacity_ah=2.0)
    self.assertEqual([0.2, 0.7, 1.0], [round(item.soc, 6) for item in labels])

def test_online_labels_reject_boundary_changes_and_nonpositive_capacity(self):
    with self.assertRaisesRegex(ValueError, "single boundary"):
        online_coulomb_labels(self.mixed_cell_points, 0.5, 2.0)
    with self.assertRaisesRegex(ValueError, "positive"):
        online_coulomb_labels(self.current_points([0], [0]), 0.5, 0.0)
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.research.test_labels -v`  
Expected: import failure for `src.research.labels`.

- [ ] **Step 3: Implement explicit offline and causal online algorithms**

在线积分采用梯形法，只使用相邻历史电流：

```python
delta_ah = 0.5 * (previous.current_a + current.current_a) * (current.timestamp_s - previous.timestamp_s) / 3600.0
soc = min(1.0, max(0.0, previous_soc + delta_ah / reference_capacity_ah))
```

函数先验证时间严格递增、所有点属于同一数据集/电芯/会话/循环、初始 SOC 位于 `[0, 1]`、参考容量为正。输出记录 `label_method`、固定容量和初始 SOC；离线算法记录使用了完整循环范围。

- [ ] **Step 4: Verify GREEN and legacy preprocessing regression**

Run: `python -m unittest tests.research.test_labels tests.test_analyze_predictions -v`  
Expected: all selected tests pass.

- [ ] **Step 5: Commit when Git is available**

```powershell
git add src/research/labels.py tests/research/test_labels.py
git commit -m "feat: add traceable offline and online SOC labels"
```

---

### Task 6: 实现泄漏防护与域安全分割

**Files:**
- Create: `src/research/leakage.py`
- Create: `src/research/splits.py`
- Test: `tests/research/test_leakage.py`
- Test: `tests/research/test_splits.py`

**Interfaces:**
- Produces: `WindowSpec`, `assert_window_boundaries(records, windows) -> None`, `assert_disjoint_domains(train, validation, test) -> None`, `fit_training_statistics(records) -> FeatureStatistics`, `assert_statistics_provenance(statistics, allowed_keys) -> None`, `leave_one_dataset_out(records) -> tuple[DomainFold, ...]`, `leave_one_cell_out(records) -> tuple[DomainFold, ...]`.
- Consumes: Task 2 `SampleRecord` and stable domain keys.

- [ ] **Step 1: Write failing leakage tests**

```python
def test_window_crossing_cells_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "window crosses"):
        assert_window_boundaries(self.records, [WindowSpec(0, 2)])

def test_train_validation_test_cell_overlap_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "cell overlap"):
        assert_disjoint_domains(self.train, self.validation_with_train_cell, self.test)

def test_statistics_provenance_rejects_test_rows(self):
    stats = fit_training_statistics(self.train + self.test)
    with self.assertRaisesRegex(ValueError, "outside training domain"):
        assert_statistics_provenance(stats, {record.key for record in self.train})
```

- [ ] **Step 2: Write failing split tests**

```python
def test_lodo_tests_each_dataset_once_without_cell_overlap(self):
    folds = leave_one_dataset_out(self.records)
    self.assertEqual({"A", "B", "C"}, {fold.test_domain for fold in folds})
    for fold in folds:
        assert_disjoint_domains(fold.train, fold.validation, fold.test)

def test_loco_is_deterministic_and_tests_each_cell_once(self):
    first = leave_one_cell_out(self.records)
    second = leave_one_cell_out(reversed(self.records))
    self.assertEqual(first, second)
    self.assertEqual(self.all_cells, {fold.test_domain for fold in first})
```

- [ ] **Step 3: Verify RED**

Run: `python -m unittest tests.research.test_leakage tests.research.test_splits -v`  
Expected: import failure for both new modules.

- [ ] **Step 4: Implement boundary identities, provenance and deterministic folds**

```python
def boundary_id(record: SampleRecord) -> tuple[str, str, str, str]:
    key = record.key
    return key.dataset_id, key.cell_id, key.session_id, key.cycle_id

def assert_disjoint_domains(train, validation, test):
    groups = [{(r.key.dataset_id, r.key.cell_id) for r in rows} for rows in (train, validation, test)]
    if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
        raise ValueError("train/validation/test cell overlap detected")
```

LODO 每个数据集恰好作为一次测试域；内部验证域从剩余数据集按字典序确定，并把其它数据集作为训练域。LOCO 每个电芯恰好作为一次测试域，验证电芯按剩余电芯字典序轮换。若数据集或电芯数量不足以产生互不重叠的三部分，抛出明确 `ValueError`，不降级为样本随机切分。

- [ ] **Step 5: Verify GREEN**

Run: `python -m unittest tests.research.test_leakage tests.research.test_splits -v`  
Expected: all selected tests pass.

- [ ] **Step 6: Commit when Git is available**

```powershell
git add src/research/leakage.py src/research/splits.py tests/research/test_leakage.py tests/research/test_splits.py
git commit -m "feat: prevent SOC domain leakage"
```

---

### Task 7: 编排第一周期审计与原子产物输出

**Files:**
- Create: `src/research/pipeline.py`
- Create: `tests/research/test_pipeline.py`
- Modify: `src/project_paths.py`
- Modify: `tests/test_project_paths.py`

**Interfaces:**
- Produces: `DataCenterPaths.research_training_dir`, `research_results_dir`, `research_runs_dir`; `run_foundation_audit(protocol_path: Path, registry_path: Path, output_dir: Path) -> dict`; CLI `python -m src.research.pipeline --protocol ... --datasets ... --output ...`.
- Consumes: Tasks 1–6.

- [ ] **Step 1: Write failing research path tests**

```python
self.assertEqual(root / "02_训练数据" / "research_v1", paths.research_training_dir)
self.assertEqual(root / "03_模型与实验结果" / "research_v1", paths.research_results_dir)
self.assertEqual(root / "04_训练平台运行记录" / "research_v1", paths.research_runs_dir)
```

- [ ] **Step 2: Verify path test RED**

Run: `python -m unittest tests.test_project_paths.DataCenterPathsTests.test_paths_read_the_configured_data_center -v`  
Expected: `AttributeError` for `research_training_dir`.

- [ ] **Step 3: Add the three path properties without changing existing properties**

```python
@property
def research_training_dir(self) -> Path:
    return self.root / "02_训练数据" / "research_v1"

@property
def research_results_dir(self) -> Path:
    return self.root / "03_模型与实验结果" / "research_v1"

@property
def research_runs_dir(self) -> Path:
    return self.root / "04_训练平台运行记录" / "research_v1"
```

- [ ] **Step 4: Verify path test GREEN**

Run: `python -m unittest tests.test_project_paths -v`  
Expected: all path tests pass.

- [ ] **Step 5: Write failing pipeline tests**

```python
def test_foundation_audit_writes_complete_traceable_artifacts(self):
    result = run_foundation_audit(self.protocol, self.registry, self.output)
    self.assertEqual("completed", result["state"])
    self.assertEqual({"manifest.json", "quality.json", "compatibility.json", "summary.md", "status.json"},
                     {path.name for path in self.output.iterdir()})
    self.assertTrue(json.loads((self.output / "status.json").read_text())["completed_at_utc"])

def test_foundation_audit_refuses_nonempty_output(self):
    self.output.mkdir()
    (self.output / "user.txt").write_text("keep", encoding="utf-8")
    with self.assertRaises(FileExistsError):
        run_foundation_audit(self.protocol, self.registry, self.output)
```

- [ ] **Step 6: Verify pipeline RED**

Run: `python -m unittest tests.research.test_pipeline -v`  
Expected: import failure for `src.research.pipeline`.

- [ ] **Step 7: Implement orchestration and failure status**

`run_foundation_audit` 顺序为：读取协议和登记表、创建空输出目录、写入 `running` 状态、逐数据集扫描清单、生成质量/兼容性结果、写中文摘要、最后原子更新为 `completed`。发生异常时写 `failed` 状态和异常类型后重新抛出。只有函数自己创建的空目录可写；非空目录一律拒绝。

CLI 参数全部必需，不从当前工作目录猜测数据位置。终端输出最终 JSON 状态；退出码由未捕获异常自然设为非零。

- [ ] **Step 8: Verify GREEN and CLI help**

Run: `python -m unittest tests.research.test_pipeline tests.test_project_paths -v`  
Expected: all selected tests pass.  
Run: `python -m src.research.pipeline --help`  
Expected: help lists `--protocol`, `--datasets`, and `--output`.

- [ ] **Step 9: Commit when Git is available**

```powershell
git add src/research/pipeline.py tests/research/test_pipeline.py src/project_paths.py tests/test_project_paths.py
git commit -m "feat: orchestrate SOC research foundation audit"
```

---

### Task 8: 合成数据端到端证据与现有资产只读审计

**Files:**
- Create: `tests/research/test_foundation_e2e.py`
- Create: `docs/research/RESEARCH_FOUNDATION.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: complete research foundation API from Tasks 1–7.
- Produces: verified synthetic end-to-end test, documented audit command, real audit output under `E:\SOC电池数据中心\03_模型与实验结果\research_v1\foundation-audit-20260721`.

- [ ] **Step 1: Write the synthetic end-to-end test**

构造三个数据集、每个数据集三个电芯、每个电芯一个会话和两个循环；其中一个记录缺温度，一个重复键，一个时间逆序。测试必须验证：清单哈希稳定、质量计数准确、在线标签不受未来电流修改影响、LODO 三折无电芯重叠、输出可从 JSON 重读。

```python
def test_three_dataset_foundation_flow_is_reproducible_and_leakage_safe(self):
    first = self.run_flow(self.root / "first")
    second = self.run_flow(self.root / "second")
    self.assertEqual(first["manifest_hashes"], second["manifest_hashes"])
    self.assertEqual(3, len(first["lodo_folds"]))
    self.assertEqual(1, first["quality"]["duplicate_key_count"])
    self.assertEqual(1, first["quality"]["time_reversal_count"])
    self.assertEqual(first["online_labels_before_cutoff"], first["labels_after_future_current_change"])
```

- [ ] **Step 2: Verify the E2E test RED for the first missing integration behavior**

Run: `python -m unittest tests.research.test_foundation_e2e -v`  
Expected: fail on the first unimplemented integration assertion, not on fixture construction.

- [ ] **Step 3: Add only the integration glue needed for GREEN**

不得为了测试向生产模块添加测试专用入口。若现有公开接口无法组合，优先简化测试夹具；只有真实用户流程也需要时，才在 `pipeline.py` 增加通用纯函数。

- [ ] **Step 4: Verify E2E GREEN and full regression**

Run: `python -m unittest tests.research.test_foundation_e2e -v`  
Expected: E2E test passes.  
Run: `python -m unittest discover -s tests -v`  
Expected: all executable tests pass; if known desktop environment tests remain blocked, record exact failing test names and error text rather than claiming a clean suite.

- [ ] **Step 5: Record protected baseline hashes before the real audit**

Run the existing project numerical environment:

```powershell
& '..\..\work\soc_venv\Scripts\python.exe' -c "from pathlib import Path; from src.evaluation.generalization_experiments import sha256_files; import json; files=[Path('results/lstm_soc.pt'),Path('results/metrics.json')]; print(json.dumps(sha256_files([p for p in files if p.is_file()]),indent=2))"
```

Save the printed mapping inside the new audit directory as `protected_hashes_before.json` through the pipeline's atomic writer, not shell redirection.

- [ ] **Step 6: Run the real read-only foundation audit**

Run:

```powershell
& '..\..\work\soc_venv\Scripts\python.exe' -m src.research.pipeline --protocol configs\research\protocol_v1.json --datasets configs\research\datasets.json --output 'E:\SOC电池数据中心\03_模型与实验结果\research_v1\foundation-audit-20260721'
```

Expected: state `completed`; output contains non-empty manifest, quality, compatibility, summary, and status files. If a registered source path is missing or unreadable, expected state is `failed`, and the missing path must be corrected in the registry from verified filesystem evidence before rerunning into a new output directory.

- [ ] **Step 7: Recompute hashes and validate artifacts**

Run the same hash command as Step 5 and compare exact mappings. Run:

```powershell
& '..\..\work\soc_venv\Scripts\python.exe' -c "from pathlib import Path; import json; p=Path(r'E:\SOC电池数据中心\03_模型与实验结果\research_v1\foundation-audit-20260721'); required=['manifest.json','quality.json','compatibility.json','summary.md','status.json']; assert all((p/n).is_file() and (p/n).stat().st_size>0 for n in required); assert json.loads((p/'status.json').read_text(encoding='utf-8'))['state']=='completed'; print('FOUNDATION_AUDIT_OK')"
```

Expected: `FOUNDATION_AUDIT_OK` and protected hash mappings identical.

- [ ] **Step 8: Document verified scope and commands**

`docs/research/RESEARCH_FOUNDATION.md` must state included datasets, audit date, compatibility decisions, label limitations, output path, test command, actual pass/fail counts, protected hash result, and the explicit statement that no new formal model was trained. `README.md` receives one short link under the existing research/generalization section; do not rewrite unrelated content.

- [ ] **Step 9: Commit when Git is available**

```powershell
git add tests/research/test_foundation_e2e.py docs/research/RESEARCH_FOUNDATION.md README.md
git commit -m "docs: verify SOC research foundation"
```

---

## Final Verification Gate

- [ ] Run `python -m unittest discover -s tests -v` and record total, passed, failed, skipped and environment-blocked tests.
- [ ] Run `python -m compileall -q src tests` and require exit code `0`.
- [ ] Run `python -m src.research.pipeline --help` and confirm all required arguments.
- [ ] Confirm the real audit directory contains exactly the registered outputs plus protected-hash evidence.
- [ ] Independently load every JSON artifact with `json.loads`.
- [ ] Compare protected baseline SHA-256 mappings before and after.
- [ ] Confirm no file beneath raw-data and historical baseline directories has a changed size or hash.
- [ ] Compare implementation against every first-cycle requirement in the approved design and list any unmet item as a blocker.

Only after this gate may the first implementation cycle be described as complete. Formal baseline/model training belongs to the next separately approved implementation plan.

