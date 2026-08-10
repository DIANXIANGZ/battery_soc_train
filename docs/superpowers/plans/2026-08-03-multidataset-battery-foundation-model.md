# 多数据集电池基础模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下载并质量审查可信公开电池数据，建立规范数据层与无泄露多目标训练，使五个目标在未见电芯/工况上按统一阈值验收。

**Architecture:** 原始数据按来源只读保存，适配器转换为统一采样级和循环级表；训练核心按电芯分组并采用嵌套验证。共享因果表征连接五个目标专属训练器，自定义 LSTM/GRU/XGBoost/Transformer 继续使用同一数据和审计协议。

**Tech Stack:** Python 3.12、NumPy、pandas、SciPy、PyTorch、scikit-learn、XGBoost、pytest。

## Global Constraints

- 训练、验证、测试按电芯/会话严格互斥，测试数据不得参与任何拟合或模型选择。
- SOC/SOE/SOH：MAE ≤0.01 且误差≤0.01的测试样本覆盖率≥0.95。
- RUL：MAE ≤1 cycle 且误差≤1 cycle的测试样本覆盖率≥0.95。
- SOT：MAE ≤平均绝对标签温度的10%，且逐样本相对阈值覆盖率≥0.95。
- 原始文件只读；现有数据和历史结果不覆盖。
- 当前目录无 Git 元数据，提交步骤记录为跳过。

---

### Task 1: 数据目录、来源清单与可重复下载器

**Files:**
- Modify: `src/project_paths.py`
- Create: `configs/research/public_battery_sources.json`
- Create: `src/data_processing/download_public_batteries.py`
- Test: `tests/test_download_public_batteries.py`

**Interfaces:**
- Produces `PublicBatterySource(source_id, landing_page, download_urls, license, targets, checksum)`.
- Produces `download_source(source, raw_root) -> dict[str, object]` with atomic `.part` download, SHA-256, byte count and manifest.

- [ ] Write failing tests asserting invalid schemes are rejected, partial files are not accepted, existing matching hashes are reused, and manifests contain source/version/license/hash.
- [ ] Run `/opt/homebrew/bin/python3.12 -m pytest tests/test_download_public_batteries.py -v`; expect import failure.
- [ ] Implement paths `public_battery_raw_dir`, `public_battery_canonical_dir`, `public_battery_reports_dir` and the downloader using argument-list `curl` calls.
- [ ] Populate sources only after official landing/download URLs and terms are verified: NASA ALT/Aging, Oxford, CALCE, MIT/Stanford, Sandia.
- [ ] Run focused tests; skip commit.

### Task 2: Raw-data quality profiler and admission decision

**Files:**
- Create: `src/data_processing/battery_data_quality.py`
- Create: `tests/test_battery_data_quality.py`

**Interfaces:**
- Produces `profile_battery_table(frame, schema) -> QualityReport` and `admit(report) -> bool`.
- Reports row/column counts, duplicates, nulls, unit/range violations, monotonicity, group coverage, time reversal, target provenance and leakage risks.

- [ ] Write failing tests for duplicate timestamps, reversed time, impossible SOC/temperature, missing cell IDs and future-derived features.
- [ ] Run focused tests; expect import failure.
- [ ] Implement critical/high/medium findings and JSON/Markdown reports; any critical group/provenance/leakage issue makes `admit=False`.
- [ ] Run focused tests; skip commit.

### Task 3: Canonical sample/cycle schemas and source adapters

**Files:**
- Create: `src/research/battery_schema.py`
- Create: `src/data_processing/adapters/{nasa_alt,oxford,calce,stanford,sandia}.py`
- Create: `src/data_processing/build_public_battery_corpus.py`
- Test: `tests/test_public_battery_adapters.py`

**Interfaces:**
- Sampling schema: `source_id, chemistry, cell_id, session_id, cycle_id, timestamp_s, voltage_v, current_a, temperature_c` plus causally derived targets.
- Cycle schema: `source_id, chemistry, cell_id, cycle_id, capacity_ah, energy_wh, soh, rul_cycles` plus historical-only features.

- [ ] Write adapter contract tests requiring stable group IDs, explicit units, sorted timestamps and source hashes.
- [ ] Run focused tests and confirm missing adapters.
- [ ] Implement each adapter independently; unsupported targets remain absent rather than imputed.
- [ ] Derive SOC/SOE by within-cycle causal integration, SOH from cell-specific initial capacity, RUL from first EOL crossing, and SOT by exact/nearest future 300-second lookup.
- [ ] Run adapter and existing NASA preparation tests; skip commit.

### Task 4: Nested group split, leakage audit and 95% coverage metrics

**Files:**
- Modify: `src/training/battery_protocol.py`
- Create: `tests/test_strict_battery_protocol.py`

**Interfaces:**
- Produces `nested_group_folds(groups, conditions, seed)`, `fit_transform_train_only`, `target_acceptance(target, reference, prediction)` and `LeakageAudit`.

- [ ] Write tests proving held-out values cannot change preprocessing/model selection and windows cannot cross group boundaries.
- [ ] Write exact coverage tests for the three acceptance rules.
- [ ] Run tests and confirm failures.
- [ ] Implement group/condition folds, train-only transformers and metric summaries with MAE/RMSE/coverage/worst-group.
- [ ] Run protocol tests; skip commit.

### Task 5: Literature-backed target specialists and domain adaptation

**Files:**
- Create: `src/training/models/{soc,soe,soh,rul,sot,domain_adaptation}.py`
- Modify: `src/training/train_nasa_state.py`, `src/training/train_nasa_lifecycle.py`, `src/training/train_nasa_hybrid.py`
- Create: `tests/test_battery_specialist_models.py`

**Interfaces:**
- Every specialist implements `fit(train, validation)`, `predict(test)` and `artifact_manifest()`.
- Domain adaptation supports MMD/CORAL fitted only from allowed training/validation domains.

- [ ] Write behavior tests for bounded SOC, causal SOE, monotonic SOH, unclipped RUL and residual SOT.
- [ ] Run focused tests and confirm missing specialist modules.
- [ ] Implement lightweight baselines first, then GRU/LSTM, TCN/Transformer and domain-adapted candidates.
- [ ] Select candidates only by nested validation score and threshold coverage, never final test performance.
- [ ] Run specialist and legacy tests; skip commit.

### Task 6: Multi-dataset experiment runner and custom-algorithm integration

**Files:**
- Create: `src/evaluation/multidataset_battery_experiments.py`
- Modify: `src/training/train_custom.py`, `src/custom_training/dataset.py`, `src/platform/platform_core.py`
- Test: `tests/test_multidataset_battery_experiments.py`, `tests/test_train_custom.py`

**Interfaces:**
- Produces smoke/formal runs with `data_manifest.json`, `split_manifest.json`, `leakage_audit.json`, `metrics_by_target.json`, `acceptance.json`, predictions and checkpoints.

- [ ] Write failing end-to-end fixtures with multiple sources/cells/conditions and an intentionally leaky feature.
- [ ] Run focused tests and confirm missing runner.
- [ ] Implement source-balanced batching, per-target availability masks, nested selection and strict held-out evaluation.
- [ ] Route custom algorithms through the same canonical schema and audit; preserve free algorithm choice.
- [ ] Run focused tests; skip commit.

### Task 7: Desktop results, smoke run, formal training and honest handoff

**Files:**
- Modify: `src/desktop/app.py`, `src/desktop/hybrid_charts.py`
- Modify: `tests/test_desktop_app.py`, `tests/test_hybrid_charts.py`

- [ ] Write UI tests requiring source coverage, five-target metrics, 95% coverage and clear pass/fail state.
- [ ] Implement the result summary without changing existing historical runs.
- [ ] Run all directly related tests.
- [ ] Download admitted datasets, produce quality reports, build the canonical corpus and run smoke training.
- [ ] Run formal nested held-out training; record actual metrics and failed targets without post-hoc test tuning.
- [ ] Run `/opt/homebrew/bin/python3.12 -m pytest -q`; separate pre-existing packaging/platform failures from regressions.
