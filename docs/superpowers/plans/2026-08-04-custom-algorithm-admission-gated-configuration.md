# 自定义算法准入门禁配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在数据与训练冻结期间交付可验证的自定义算法选择、字段角色配置、集中注册、准入报告和不可绕过的运行阻塞，同时完整保留 LSTM、GRU、XGBoost、Transformer 后台路由代码。

**Architecture:** `src/custom_training` 增加纯配置层：集中算法注册表描述四算法，字段角色映射保留电池 identity/provenance，纯函数 admission engine 输出逐目标阻塞原因。`PlatformStore` 只持久化配置和未授权准入状态；桌面端展示算法栏与门禁报告。训练命令和 `TrainingController` 前均执行硬门禁，当前阶段不启动任何模型拟合。

**Tech Stack:** Python 3.12、dataclasses、Tkinter/ttk、JSON、pandas（只用于已有导入校验）、unittest/pytest、subprocess 参数列表；XGBoost 继续使用无 Torch 的隔离解释器。

## Global Constraints

- 交付条件目标时间：2026-08-05 18:00（Asia/Shanghai）；建议内部完成时间 16:30，保留 1.5 小时复核缓冲。
- 不修改 public battery v11 数据、标签、provenance、阈值或训练结果。
- v11 必须保持 `valid_for_training=false`、`training_authorized=false`。
- 5 个 MATR `official_continuation` 电芯不得启动 RUL smoke/formal training，也不得声称 `<=1-cycle`。
- 36 个 MATR 候选与 5 个早停继续 `right_censored`；不得升级或作精确点监督。
- Oxford 当前数据仅允许 100-cycle-grid/interval-censored 诊断，不进入 1-cycle 点误差验收。
- 本计划实施阶段只运行纯函数、配置持久化、UI 和 mock 调度测试；禁止调用 `run_training`、真实 XGBoost/LSTM/GRU/Transformer 拟合或任何 smoke/formal training。
- XGBoost 后台必须保留单独无 Torch 解释器、`nthread=1`；不得回退到与 Torch 同进程拟合。
- 算法推荐只作建议，用户可覆盖；覆盖仅改变配置，不授予训练权限。
- 算法、目标或字段角色变化必须使旧 admission 失效。
- 当前 checkout 不是 Git 仓库；每个任务以测试输出和文件哈希作为审阅断点，不执行 Git commit。

---

## File Structure

- Create: `src/custom_training/algorithms.py` — 四算法唯一注册表、显示名、推荐逻辑和隔离属性。
- Create: `src/custom_training/admission.py` — 纯函数式目标门禁与可序列化 admission report。
- Modify: `src/custom_training/dataset.py` — 引用唯一算法注册；保存/导出 metadata role 映射，不把 identity/provenance 强制数值化。
- Modify: `src/platform/platform_core.py` — 配置更新、admission 失效、命令创建前硬门禁。
- Modify: `src/desktop/app.py` — 自定义项目算法配置栏、角色映射摘要、阻塞原因和禁用态运行按钮。
- Modify: `src/training/train_custom.py` — 只改为从统一注册表读取算法 key；保留四算法训练实现和 XGBoost 隔离调用，不在本阶段执行。
- Create: `tests/test_custom_training_admission.py` — 注册表、目标门禁、RUL/Oxford/v11 阻塞纯函数测试。
- Modify: `tests/test_custom_dataset.py` — metadata role 导出与算法注册一致性。
- Modify: `tests/test_platform_core.py` — 算法配置持久化、admission 失效、run 目录创建前阻塞、授权后命令预览。
- Modify: `tests/test_desktop_app.py` — 算法栏、建议覆盖、阻塞态 UI 与 mock controller 不启动测试。
- Preserve: `src/training/xgboost_backend.py` — 不修改实际拟合路径；增加静态约束测试即可。
- Update: `docs/audits/custom_algorithm_training_scope_inventory.md` — 实施后补充文件哈希和测试结果，不改变数据结论。

---

### Task 1: 集中算法注册与纯函数 target admission

**Files:**
- Create: `src/custom_training/algorithms.py`
- Create: `src/custom_training/admission.py`
- Create: `tests/test_custom_training_admission.py`
- Modify: `src/custom_training/dataset.py`
- Modify: `src/training/train_custom.py`

**Interfaces:**
- Produces `AlgorithmSpec(key: str, label: str, family: str, isolated_worker: bool, recommended_targets: tuple[str, ...])`.
- Produces `ALGORITHM_REGISTRY: dict[str, AlgorithmSpec]` and `algorithm_keys() -> tuple[str, ...]`.
- Produces `recommend_algorithm(targets: tuple[str, ...]) -> str`.
- Produces `TargetAdmission(target: str, configuration_allowed: bool, training_allowed: bool, blockers: tuple[str, ...], warnings: tuple[str, ...])`.
- Produces `CustomTrainingAdmission(configuration_allowed: bool, training_allowed: bool, generalization_level: str, targets: tuple[TargetAdmission, ...])`.
- Produces `assess_custom_training(config: CustomDatasetConfig, *, manifest: dict[str, object] | None = None) -> CustomTrainingAdmission`.

- [ ] **Step 1: Write the failing registry and admission tests**

```python
from src.custom_training.admission import assess_custom_training
from src.custom_training.algorithms import ALGORITHM_REGISTRY, algorithm_keys, recommend_algorithm
from src.custom_training.dataset import CustomDatasetConfig


def config(targets=("soc",), algorithm="lstm", roles=()):
    return CustomDatasetConfig(
        source_path=Path("cell.csv"), sheet_name=None, time_column="time",
        feature_columns=("voltage", "current"), target_columns=targets,
        algorithm=algorithm, role_columns=roles,
    )


def test_algorithm_registry_is_the_single_four_algorithm_contract():
    assert algorithm_keys() == ("lstm", "gru", "xgboost", "transformer")
    assert ALGORITHM_REGISTRY["xgboost"].isolated_worker is True
    assert recommend_algorithm(("rul_cycles",)) == "xgboost"
    assert recommend_algorithm(("soc", "soe")) == "lstm"


def test_user_algorithm_override_is_configuration_only():
    result = assess_custom_training(config(algorithm="transformer"))
    assert result.configuration_allowed is True
    assert result.training_allowed is False
    assert "manifest_missing" in result.targets[0].blockers


def test_v11_frozen_manifest_blocks_rul_even_with_observed_rows():
    result = assess_custom_training(
        config(
            targets=("rul_cycles",), algorithm="xgboost",
            roles=(("cell_id", "cell"), ("cycle_id", "cycle"),
                   ("rul_observed", "observed"), ("eol_provenance", "provenance")),
        ),
        manifest={
            "valid_for_training": False,
            "training_authorized": False,
            "rul": {"exact_observed_cells": 5, "grid_cycles": 1},
        },
    )
    assert result.training_allowed is False
    assert "dataset_frozen" in result.targets[0].blockers
    assert "insufficient_exact_rul_cells" in result.targets[0].blockers


def test_oxford_grid_is_not_one_cycle_point_supervision():
    result = assess_custom_training(
        config(targets=("rul_cycles",), algorithm="xgboost"),
        manifest={
            "valid_for_training": True,
            "training_authorized": True,
            "rul": {"exact_observed_cells": 8, "grid_cycles": 100, "task": "point"},
        },
    )
    assert result.training_allowed is False
    assert "rul_grid_not_one_cycle" in result.targets[0].blockers
```

- [ ] **Step 2: Run the tests to verify RED without invoking any trainer**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest -q tests/test_custom_training_admission.py
```

Expected: FAIL during import because `algorithms.py` and `admission.py` do not exist.

- [ ] **Step 3: Implement the minimal immutable algorithm registry**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AlgorithmSpec:
    key: str
    label: str
    family: str
    isolated_worker: bool
    recommended_targets: tuple[str, ...]


ALGORITHM_REGISTRY = {
    "lstm": AlgorithmSpec("lstm", "LSTM", "sequence", False, ("soc", "soe", "sot")),
    "gru": AlgorithmSpec("gru", "GRU", "sequence", False, ("soc", "soe", "sot")),
    "xgboost": AlgorithmSpec("xgboost", "XGBoost", "tabular_window", True, ("soh", "rul")),
    "transformer": AlgorithmSpec("transformer", "Transformer", "sequence", False, ("soc", "soe", "sot", "soh")),
}


def algorithm_keys() -> tuple[str, ...]:
    return tuple(ALGORITHM_REGISTRY)


def recommend_algorithm(targets: tuple[str, ...]) -> str:
    normalized = tuple(value.strip().lower() for value in targets)
    return "xgboost" if normalized and all("rul" in value or "soh" in value for value in normalized) else "lstm"
```

- [ ] **Step 4: Implement a fail-closed admission report**

Required rules:

```python
STANDARD_ROLES = frozenset({
    "cell_id", "session_id", "cycle_id", "condition_id",
    "rul_observed", "eol_provenance",
})
BATTERY_TARGETS = frozenset({"soc", "soe", "soh", "sot", "sot_c", "sot_5min_c", "rul", "rul_cycles"})
MINIMUM_EXACT_RUL_CELLS = 6


def assess_custom_training(config, *, manifest=None):
    roles = dict(config.role_columns)
    manifest = manifest or {}
    global_blockers = []
    if not manifest:
        global_blockers.append("manifest_missing")
    if manifest.get("valid_for_training") is not True or manifest.get("training_authorized") is not True:
        global_blockers.append("dataset_frozen")
    if "cell_id" not in roles or "condition_id" not in roles:
        global_blockers.append("strict_group_split_unavailable")
    generalization_level = (
        "unseen_cell_and_condition"
        if "strict_group_split_unavailable" not in global_blockers
        else "configuration_only"
    )
    target_results = []
    for original_target in config.target_columns:
        key = original_target.strip().lower()
        blockers = list(global_blockers)
        required_roles = {"cell_id", "condition_id"}
        if key in {"soc", "soe", "sot", "sot_c", "sot_5min_c"}:
            required_roles.update({"session_id", "cycle_id"})
        if key in {"soh", "rul", "rul_cycles"}:
            required_roles.add("cycle_id")
        if key in {"rul", "rul_cycles"}:
            required_roles.update({"rul_observed", "eol_provenance"})
        missing_roles = sorted(required_roles - set(roles))
        blockers.extend(f"missing_role:{role}" for role in missing_roles)
        target_manifest = manifest.get("targets", {}).get(original_target, {})
        if key in BATTERY_TARGETS and target_manifest.get("causal_label_audit_passed") is not True:
            blockers.append("causal_label_audit_missing")
        if key in {"rul", "rul_cycles"}:
            rul = manifest.get("rul", {})
            if int(rul.get("exact_observed_cells", 0)) < MINIMUM_EXACT_RUL_CELLS:
                blockers.append("insufficient_exact_rul_cells")
            if int(rul.get("grid_cycles", 0)) != 1:
                blockers.append("rul_grid_not_one_cycle")
            if rul.get("task") != "point":
                blockers.append("rul_not_exact_point_task")
            if rul.get("censored_rows_are_exact_supervision") is not False:
                blockers.append("rul_censoring_contract_missing")
        if key not in BATTERY_TARGETS:
            required_semantics = ("unit", "prediction_time", "acceptance_rule")
            missing_semantics = [name for name in required_semantics if not target_manifest.get(name)]
            blockers.extend(f"custom_target_missing:{name}" for name in missing_semantics)
        blockers = tuple(dict.fromkeys(blockers))
        target_results.append(TargetAdmission(
            target=original_target,
            configuration_allowed=True,
            training_allowed=not blockers,
            blockers=blockers,
            warnings=(),
        ))
    return CustomTrainingAdmission(
        configuration_allowed=config.algorithm in ALGORITHM_REGISTRY and bool(config.target_columns),
        training_allowed=bool(target_results) and all(item.training_allowed for item in target_results),
        generalization_level=generalization_level,
        targets=tuple(target_results),
    )
```

The implementation must return these concrete blocker keys and must not auto-authorize any current v11 or Oxford manifest.

- [ ] **Step 5: Replace duplicated algorithm tuples with registry-derived keys**

In `dataset.py` and `train_custom.py`, import `algorithm_keys` and set the existing public constants from it. Do not alter `run_training`, model definitions or `xgboost_backend` invocation.

- [ ] **Step 6: Run the pure tests to verify GREEN**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest -q tests/test_custom_training_admission.py tests/test_custom_dataset.py -k 'not training'
```

Expected: PASS; no `run_training`, Torch model fit or XGBoost process appears in captured output.

---

### Task 2: Preserve battery metadata roles and persist configuration-only algorithm changes

**Files:**
- Modify: `src/custom_training/dataset.py`
- Modify: `src/platform/platform_core.py`
- Modify: `tests/test_custom_dataset.py`
- Modify: `tests/test_platform_core.py`

**Interfaces:**
- Extends `CustomDatasetConfig` with `role_columns: tuple[tuple[str, str], ...] = ()`.
- Produces `canonical_role_mapping(config: CustomDatasetConfig) -> dict[str, str]`.
- Produces `PlatformStore.update_custom_algorithm(project: Project, algorithm: str) -> dict`.
- Produces `PlatformStore.custom_admission_for(project: Project) -> dict`.
- Produces `PlatformStore.require_custom_training_admission(project: Project) -> dict`.

- [ ] **Step 1: Write failing metadata export and persistence tests**

```python
def test_metadata_roles_are_renamed_and_not_numeric_cast(tmp_path):
    source = tmp_path / "cells.csv"
    source.write_text(
        "cell,condition,cycle,observed,provenance,v,i,rul\n"
        "A,cold,1,1,official_continuation,3.7,1.0,10\n" * 30,
        encoding="utf-8",
    )
    cfg = CustomDatasetConfig(
        source, None, None, ("v", "i"), ("rul",), "xgboost",
        role_columns=(("cell_id", "cell"), ("condition_id", "condition"),
                      ("cycle_id", "cycle"), ("rul_observed", "observed"),
                      ("eol_provenance", "provenance")),
    )
    validate_and_export(cfg, tmp_path / "out.csv")
    assert (tmp_path / "out.csv").read_text().splitlines()[0] == (
        "cell_id,condition_id,cycle_id,rul_observed,eol_provenance,v,i,rul"
    )


def test_algorithm_update_persists_and_invalidates_admission(tmp_path):
    store, project = make_custom_project(tmp_path, algorithm="lstm")
    record = store.update_custom_algorithm(project, "gru")
    assert record["custom_config"]["algorithm"] == "gru"
    assert record["custom_admission"]["training_allowed"] is False
    assert "configuration_changed" in record["custom_admission"]["blockers"]
```

- [ ] **Step 2: Run the targeted tests and verify RED**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_custom_dataset.py::CustomDatasetTests::test_metadata_roles_are_renamed_and_not_numeric_cast \
  tests/test_platform_core.py::PlatformStoreTests::test_algorithm_update_persists_and_invalidates_admission
```

Expected: FAIL because the new config field and store methods are absent.

- [ ] **Step 3: Implement role validation and export**

Rules:

- role keys must be unique and limited to the declared canonical roles;
- one source column cannot serve two roles or overlap a feature/target except the existing time mapping;
- `cell_id`, `session_id`, `condition_id` and `eol_provenance` remain strings;
- `cycle_id` and `rul_observed` must be numeric after conversion;
- exported role columns use canonical names and precede features/targets;
- configuration changes never mutate the original source file.

- [ ] **Step 4: Implement algorithm update with automatic admission invalidation**

`update_custom_algorithm` must validate the key through `ALGORITHM_REGISTRY`, update only that project's `custom_config.algorithm`, and atomically replace `custom_admission` with:

```python
{
    "configuration_allowed": True,
    "training_allowed": False,
    "blockers": ["configuration_changed", "chief_engineer_approval_required"],
}
```

- [ ] **Step 5: Implement the defense-in-depth admission accessor**

`require_custom_training_admission` must return the saved report only when `training_allowed is True`; otherwise raise `ValueError("自定义训练仍被数据准入门禁阻塞。")`. It must not infer authorization from an algorithm choice.

- [ ] **Step 6: Run the targeted non-training tests to verify GREEN**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest -q tests/test_custom_dataset.py tests/test_platform_core.py \
  -k 'custom and not algorithms_write_a_common_result_contract'
```

Expected: PASS; no model trainer subprocess is started.

---

### Task 3: Add the training-page algorithm bar and block runtime before run creation

**Files:**
- Modify: `src/desktop/app.py`
- Modify: `src/platform/platform_core.py`
- Modify: `tests/test_desktop_app.py`
- Modify: `tests/test_platform_core.py`

**Interfaces:**
- Produces `DesktopTrainingApp._custom_project_state() -> tuple[dict, CustomTrainingAdmission]`.
- Produces `DesktopTrainingApp._save_custom_algorithm() -> None`.
- `build_custom_command(...)` consumes a persisted, authorized admission and refuses before `create_run_dir` otherwise.

- [ ] **Step 1: Write failing UI and pre-run gate tests**

```python
def test_custom_training_page_exposes_algorithm_config_but_disables_run_when_blocked():
    app = make_custom_app_with_project(algorithm="lstm", training_allowed=False)
    app.show_training()
    assert app.custom_algorithm_var.get() == "lstm"
    assert str(app.start_button.cget("state")) == "disabled"
    assert "数据准入门禁" in app.custom_admission_text.get()


def test_blocked_custom_command_creates_no_run_directory(tmp_path):
    store, project = make_custom_project(tmp_path, algorithm="gru")
    runs = project.path / "runs"
    before = tuple(runs.iterdir())
    with pytest.raises(ValueError, match="数据准入门禁"):
        build_custom_command(project, {}, Path("python"))
    assert tuple(runs.iterdir()) == before


def test_blocked_custom_start_never_calls_controller():
    app = make_custom_app_with_project(algorithm="gru", training_allowed=False)
    app.controller = Mock()
    app.start_training()
    app.controller.start.assert_not_called()
```

- [ ] **Step 2: Run the three tests and verify RED**

Expected: FAIL because the UI state and pre-run admission requirement are absent.

- [ ] **Step 3: Render the minimal custom configuration card**

For custom projects, `show_training()` must render before generic numeric parameters:

- selected targets and mapped identity/provenance roles;
- a readonly combobox backed by `algorithm_keys()`;
- recommendation label from `recommend_algorithm()`;
- “保存算法配置” button;
- admission summary showing generalization level and blocker keys in Chinese;
- disabled “开始训练” button whenever `training_allowed` is false.

Do not add auto-tuning, model execution, data download, provenance editing or an “approve” control.

- [ ] **Step 4: Enforce the same gate in `build_custom_command`**

Call `require_custom_training_admission` before `create_run_dir`. UI state must not be the only protection. An unauthorized direct Python call must also fail without creating a run directory.

- [ ] **Step 5: Preserve algorithm routing without executing it**

For a temporary test record whose admission is explicitly set true by the test fixture, assert the built argument list contains:

```python
assert command[command.index("--algorithm") + 1] == "transformer"
assert command[command.index("--targets") + 1:]  # selected targets remain present
```

The test must stop after command construction; it must not call `TrainingController.start`.

- [ ] **Step 6: Run UI/store tests with mocked controller**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest -q tests/test_desktop_app.py tests/test_platform_core.py \
  -k 'custom or algorithm or admission'
```

Expected: PASS or display-dependent UI tests SKIP with an explicit Tk display reason; controller start count remains zero.

---

### Task 4: Freeze-safe verification, static isolation checks and delivery evidence

**Files:**
- Modify: `tests/test_custom_training_admission.py`
- Modify: `docs/audits/custom_algorithm_training_scope_inventory.md`

**Interfaces:**
- Produces a reviewable test log and file-hash manifest; no training artifacts.

- [ ] **Step 1: Add a static XGBoost isolation regression**

```python
def test_xgboost_worker_remains_torch_free_and_single_threaded():
    source = Path("src/training/xgboost_backend.py").read_text(encoding="utf-8")
    assert "import torch" not in source
    assert 'if "torch" in sys.modules' in source
    assert '"nthread": 1' in source
    parent = Path("src/training/train_custom.py").read_text(encoding="utf-8")
    assert '"-m", "src.training.xgboost_backend"' in parent
```

- [ ] **Step 2: Add a test proving no current v11/Oxford configuration is authorized**

Use the fixed audit facts only: v11 `valid_for_training=false`, MATR exact observed cells=5, Oxford grid=100. Assert both admission reports remain false.

- [ ] **Step 3: Run the freeze-safe suite only**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_custom_training_admission.py \
  tests/test_custom_dataset.py \
  tests/test_platform_core.py \
  tests/test_desktop_app.py \
  -k 'not algorithms_write_a_common_result_contract and not canonical_group_columns_enable_strict_cell_condition_split'
```

Forbidden during this task:

- `tests/test_train_custom.py::CustomTrainingTests::test_algorithms_write_a_common_result_contract`;
- any direct call to `run_training`;
- any smoke/formal evaluator;
- any new data download or public corpus rebuild.

- [ ] **Step 4: Search for bypasses and placeholder text**

Run:

```bash
rg -n "create_run_dir|controller\.start|build_custom_command|training_allowed" src tests
rg -n "TBD|TODO|implement later|fill in details" \
  docs/superpowers/plans/2026-08-04-custom-algorithm-admission-gated-configuration.md \
  src/custom_training tests/test_custom_training_admission.py
```

Expected: every custom execution path reaches a backend gate before run creation; no placeholder remains in implementation files.

- [ ] **Step 5: Record test output and hashes**

Append to `docs/audits/custom_algorithm_training_scope_inventory.md`:

- exact test command and exit status;
- PASS/SKIP counts;
- SHA-256 for modified source and test files;
- explicit statement that no model, run directory, corpus or provenance was created/changed.

- [ ] **Step 6: Stop and request chief-engineer review**

Report only configuration/UI/registry/gate completion. Do not claim custom training capability is released, and do not start any trainer until a separate target-specific data admission and training approval exists.

---

## Test Matrix

| Area | Test type | Real training? | Required result |
|---|---|---:|---|
| Algorithm registry | Pure unit | No | Four stable keys; XGBoost marked isolated |
| Recommendation/override | Pure unit | No | Suggestion deterministic; override saves config only |
| Metadata role export | Temp CSV | No | Identity/provenance preserved and renamed; no numeric cast on strings |
| Admission reports | Pure unit | No | v11, 5-cell MATR RUL and Oxford grid remain blocked |
| Config persistence | Temp project registry | No | Algorithm update persists and invalidates old admission |
| Backend hard gate | Temp project registry | No | Block occurs before run directory creation |
| UI state | Tk or source-backed unit | No | Selector visible; blockers visible; start disabled |
| Controller boundary | Mock | No | `controller.start` never called when blocked |
| Authorized command preview | Temp config only | No | Correct algorithm/targets in argument list; no subprocess |
| XGBoost isolation | Static source assertion | No | No Torch import; clean worker guard; `nthread=1` |
| Existing real trainer tests | Excluded | Yes | Must not run before separate approval |

## Estimate and Delivery Boundary

| Work item | Estimate |
|---|---:|
| Task 1 — registry + pure admission | 1.5 h |
| Task 2 — metadata roles + persistence | 2.0 h |
| Task 3 — UI algorithm bar + hard gate | 2.5 h |
| Task 4 — freeze-safe verification/evidence | 1.0 h |
| Contingency for Tk/platform compatibility | 1.0 h |
| **Total after approval** | **8.0 h** |

If approved no later than 2026-08-05 08:30 Asia/Shanghai, the configuration/UI/registry/gate deliverable is expected by 2026-08-05 16:30, leaving 1.5 hours before the 18:00 deadline for chief-engineer review. Strict MATR/Oxford RUL training and `<=1-cycle` acceptance are external-data blocked and explicitly excluded from this estimate and commitment.

## Self-Review

- Spec coverage: algorithm selector, user override, role mapping, persistence, target gates, XGBoost isolation, UI/backend blocking and non-training tests are covered.
- Excluded intentionally: model fitting, hyperparameter tuning, result charts and RUL accuracy claims; each requires later training/data approval.
- Type consistency: `AlgorithmSpec`, `TargetAdmission`, `CustomTrainingAdmission`, `role_columns`, store methods and UI consumers use the same names throughout.
- Scope discipline: no public data, label, provenance, model or threshold modification is included.

Plan complete and awaiting chief-engineer approval. Implementation must use TDD task-by-task and stop at each failing gate.
