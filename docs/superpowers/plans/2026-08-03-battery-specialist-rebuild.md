# 电池专属模型无泄露重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 SOC、SOE、SOH、RUL、SOT 建立独立因果模型，同时保留自定义数据集的算法选择并统一防泄露评估。

**Architecture:** 将现有 `train_nasa_state`、`train_nasa_lifecycle` 拆为目标专属训练器，由 `train_nasa_hybrid` 只负责编排四折 LOCO、审计和汇总。自定义训练共享同一切分、归一化、指标和验收模块，但仍可选择 LSTM/GRU/XGBoost/Transformer。

**Tech Stack:** Python、NumPy、PyTorch、scikit-learn、XGBoost、pytest。

## Global Constraints

- 测试电芯不得参与任何拟合、标准化、早停或调参。
- SOC/SOE/SOH MAE ≤1%，RUL MAE ≤1 cycle，SOT 绝对 MAE ≤标签温度的10%。
- 历史结果与基线文件只读，不覆盖。
- 当前目录无 Git 元数据；每个提交步骤记录为跳过。

---

### Task 1: 统一因果切分、特征审计与验收协议

**Files:**
- Create: `src/training/battery_protocol.py`
- Create: `tests/test_battery_protocol.py`

**Interfaces:**
- Produces `CausalSplit(train_cells, validation_cell, test_cell)`, `fit_normalizer(train: np.ndarray)`, `assert_no_group_overlap(split)`, `acceptance(target, mae, label_values) -> dict`。

- [ ] Write failing tests proving test-cell values cannot alter fitted normalizers or validation choices.
- [ ] Run: `python3.12 -m pytest tests/test_battery_protocol.py -v`; expected import failure.
- [ ] Implement chronological group split, train-only normalizer, target thresholds and audit manifest.
- [ ] Run focused tests; expected pass.
- [ ] Skip Git commit because no repository exists.

### Task 2: SOC/SOE/SOT 专属因果状态训练器

**Files:**
- Modify: `src/training/train_nasa_state.py`
- Create: `tests/test_battery_state_specialists.py`

**Interfaces:**
- Produces `run_soc_fold`, `run_soe_fold`, `run_sot_fold`, each returning `{metrics, predictions, baseline_metrics, audit}`.

- [ ] Write tests that reject windows crossing cells/cycles, verify SOC bounds, verify SOE has no future energy feature, and verify SOT equals `last_temperature + predicted_delta`.
- [ ] Run focused tests and confirm failure.
- [ ] Implement GRU SOC, causal energy estimator, and independent residual SOT model with train-only normalization.
- [ ] Run focused tests and existing `tests/test_train_nasa_state.py`.
- [ ] Skip Git commit.

### Task 3: SOH/RUL 专属退化模型

**Files:**
- Modify: `src/training/train_nasa_lifecycle.py`
- Create: `tests/test_battery_lifecycle_specialists.py`

**Interfaces:**
- Produces `run_soh_fold` and `run_rul_fold`; RUL returns `fallback_used` and may exceed all observed training RUL labels.

- [ ] Write tests proving features exclude future cycles and RUL is not clipped to the training-label range.
- [ ] Run focused tests and confirm failure.
- [ ] Implement monotonic SOH trajectory estimator and EOL-threshold RUL extrapolator using training-only priors.
- [ ] Run focused tests and existing lifecycle tests.
- [ ] Skip Git commit.

### Task 4: LOCO orchestration, audit artifacts and threshold result page

**Files:**
- Modify: `src/training/train_nasa_hybrid.py`
- Modify: `src/desktop/app.py`
- Modify: `src/desktop/hybrid_charts.py`
- Modify: `tests/test_train_nasa_hybrid.py`, `tests/test_desktop_app.py`

- [ ] Write tests requiring every fold/target to contain predictions, baseline, audit and acceptance verdict.
- [ ] Run focused tests and confirm failure.
- [ ] Wire five specialists into the four-fold runner; write `leakage_audit.json`, `acceptance.json`, target charts and explicit pass/fail UI.
- [ ] Run hybrid and desktop tests.
- [ ] Skip Git commit.

### Task 5: Custom algorithms adopt the same battery protocol

**Files:**
- Modify: `src/custom_training/dataset.py`
- Modify: `src/training/train_custom.py`
- Modify: `src/desktop/app.py`
- Modify: `tests/test_custom_dataset.py`, `tests/test_train_custom.py`

- [ ] Write tests that custom grouped data uses group isolation, ungrouped data reports time-only generalization, and all four algorithms emit an audit/acceptance artifact.
- [ ] Run focused tests and confirm failure.
- [ ] Add optional cell/session mapping, causal feature recommendations and shared protocol output without limiting algorithm selection.
- [ ] Run custom-data tests.
- [ ] Skip Git commit.

### Task 6: Full evidence run

- [ ] Run the complete suite with `/opt/homebrew/bin/python3.12 -m pytest -v`.
- [ ] Run a NASA four-fold smoke experiment and inspect all five `acceptance.json` entries.
- [ ] Report achieved metrics separately from thresholds; do not claim success for targets that fail.
