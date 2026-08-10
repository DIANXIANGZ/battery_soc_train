# NASA Hybrid Five-State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the short-window five-head NASA trainer in the desktop workflow with one intuitive hybrid workflow that evaluates SOC, SOE, five-minute-ahead temperature, SOH, and RUL across four held-out cells.

**Architecture:** Keep sample-level electrical states, future temperature, and lifecycle health in separate models and combine their artifacts through a single four-fold LOCO orchestrator. The desktop presents one improved NASA project, reads one run directory, and renders five four-cell comparison charts while preserving the old five-head result as a frozen baseline.

**Tech Stack:** Python 3.11+, PyTorch, NumPy, scikit-learn, Pillow, Tkinter, `unittest`.

## Global Constraints

- `sot_5min_c` means the first measured temperature at least 300 seconds after the current sample.
- RW9, RW10, RW11, and RW12 must rotate through four leak-free LOCO folds.
- New runs must never overwrite the old five-head result directory.
- Formal aggregate metrics are unweighted macro means across four held-out cells.
- A completed run may report that a model loses to its baseline; the UI must show that result as a warning.
- The extracted source has no `.git` metadata, so each task ends with a verification checkpoint instead of a Git commit.

---

### Task 1: Enforce the future-temperature data contract

**Files:**
- Modify: `src/data_processing/prepare_nasa_lifecycle.py`
- Modify: `tests/test_prepare_nasa_lifecycle.py`

**Interfaces:**
- Consumes: `first_future_temperature(time_s, temperature_c, index, horizon_s)`.
- Produces: `validate_future_temperature_rows(rows: list[dict[str, object]], horizon_s: float) -> None` and audit fields `sot_horizon_s`, `future_temperature_identity_count`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_future_temperature_contract_rejects_current_temperature_identity(self):
    rows = [{"time_s": 0.0, "temperature_c": 20.0, "sot_5min_c": 20.0}]
    with self.assertRaisesRegex(ValueError, "current temperature"):
        validate_future_temperature_rows(rows, horizon_s=300.0)

def test_future_temperature_uses_first_sample_at_or_after_horizon(self):
    time_s = np.array([0.0, 299.0, 301.0])
    temperature = np.array([20.0, 21.0, 22.0])
    self.assertEqual(first_future_temperature(time_s, temperature, 0, 300.0), 22.0)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_prepare_nasa_lifecycle -v`

Expected: import or assertion failure because `validate_future_temperature_rows` does not exist.

- [ ] **Step 3: Implement the contract validation**

Add a validator that rejects empty rows, non-positive horizons, missing fields, and a dataset where every `sot_5min_c` equals `temperature_c` within `1e-9`. Call it before writing the state CSV and record the identity count and 300-second horizon in the audit.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m unittest tests.test_prepare_nasa_lifecycle -v`

Expected: all lifecycle preparation tests pass.

---

### Task 2: Separate SOC/SOE from a persistence-residual temperature model

**Files:**
- Modify: `src/training/train_nasa_state.py`
- Modify: `tests/test_train_nasa_state.py`

**Interfaces:**
- Consumes: leak-safe state windows from `make_state_sequences`.
- Produces: `ElectricalStateLSTM`, `TemperatureResidualLSTM`, `temperature_features`, and `run_state_fold` artifacts under sibling `state/` and `temperature/` directories.

- [ ] **Step 1: Write failing residual and artifact tests**

```python
def test_temperature_prediction_adds_delta_to_last_observation(self):
    last = torch.tensor([20.0, 25.0])
    delta = torch.tensor([0.5, -1.0])
    self.assertTrue(torch.equal(compose_future_temperature(last, delta), torch.tensor([20.5, 24.0])))

def test_temperature_features_are_causal(self):
    block = np.array([[3.7, -1.0, 20.0, 0.0], [3.6, -1.0, 21.0, -0.1]], dtype=np.float32)
    values = temperature_features(block)
    self.assertAlmostEqual(float(values[-1]), 1.0)
```

Extend the training artifact test to require `test_predictions.csv`, `persistence_metrics.json`, and separate best-validation histories for electrical and temperature models.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_train_nasa_state -v`

Expected: failures for missing `compose_future_temperature`, `temperature_features`, and prediction artifacts.

- [ ] **Step 3: Implement the two specialized models**

Use one LSTM with two heads for normalized SOC/SOE. Use a second LSTM for temperature delta with causal inputs `(voltage, current, temperature, dv_dt, power, temperature_change, temperature_slope)`. Compose its output with the final observed temperature. Select each checkpoint using its own validation loss and save sample-level reference, prediction, and persistence columns.

- [ ] **Step 4: Add target-specific early stopping**

Stop each model after six validation epochs without improvement in formal mode; smoke mode still runs one epoch. Store `best_epoch`, `best_validation_loss`, and `epochs_completed` separately.

- [ ] **Step 5: Run and verify GREEN**

Run: `python -m unittest tests.test_train_nasa_state -v`

Expected: all state tests pass and real prediction rows are written.

---

### Task 3: Replace direct tree RUL regression with causal threshold projection

**Files:**
- Modify: `src/training/train_nasa_lifecycle.py`
- Modify: `tests/test_train_nasa_lifecycle.py`

**Interfaces:**
- Consumes: cycle rows ordered by `(cell_id, cycle_index)`.
- Produces: `RulTrajectoryEstimator.fit(train_rows)`, `predict(test_rows)`, and per-row fallback metadata.

- [ ] **Step 1: Write failing extrapolation and causality tests**

```python
def test_rul_trajectory_can_exceed_training_label_maximum(self):
    estimator = RulTrajectoryEstimator(eol_soh=0.70).fit(training_rows)
    prediction = estimator.predict(long_life_rows)
    self.assertGreater(float(prediction[0]), max(float(row["rul_cycles"]) for row in training_rows))

def test_rul_prediction_for_cycle_is_unchanged_by_future_test_rows(self):
    first = estimator.predict(test_rows[:4])[-1]
    extended = estimator.predict(test_rows[:8])[3]
    self.assertAlmostEqual(float(first), float(extended))
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_train_nasa_lifecycle -v`

Expected: failure because `RulTrajectoryEstimator` is absent.

- [ ] **Step 3: Implement the causal estimator**

For each test cycle, fit a robust linear slope to only the available `soh` history versus `cycle_index`. Constrain the negative slope to the 10th–90th percentile of negative slopes observed in training cells. Predict threshold crossing `(current_soh - 0.70) / -slope`; use the training median negative slope when fewer than three history points exist or the local slope is non-negative. Do not clip to the maximum training RUL.

- [ ] **Step 4: Keep SOH regression and write audit metadata**

Retain the cycle-feature SOH regressor. Replace only the RUL branch. Add `rul_method`, `slope_used`, and `used_prior_fallback` columns to predictions and summarize fallback counts in `run_config.json`.

- [ ] **Step 5: Run and verify GREEN**

Run: `python -m unittest tests.test_train_nasa_lifecycle -v`

Expected: all lifecycle training tests pass, including causal prefix invariance and extrapolation.

---

### Task 4: Add one hybrid four-fold training command

**Files:**
- Create: `src/training/train_nasa_hybrid.py`
- Modify: `src/evaluation/nasa_lifecycle_experiments.py`
- Create: `tests/test_train_nasa_hybrid.py`
- Modify: `tests/test_nasa_lifecycle_experiments.py`

**Interfaces:**
- Consumes: `--state-data`, `--lifecycle-data`, `--results-dir`, `--stage`, and `--seed`.
- Produces: one self-contained run directory with four folds, aggregate metrics, report, config, and immutable-baseline hashes.

- [ ] **Step 1: Write failing aggregation tests**

```python
def test_aggregate_reports_macro_mean_worst_fold_and_baseline(self):
    result = aggregate_target_metrics(fold_metrics, fold_baselines)
    self.assertEqual(result["fold_count"], 4)
    self.assertEqual(result["worst_fold"], "test_RW12")
    self.assertIn("beats_baseline", result)

def test_hybrid_cli_requires_explicit_results_directory(self):
    with self.assertRaises(SystemExit):
        parse_args(["--stage", "smoke"])
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_train_nasa_hybrid tests.test_nasa_lifecycle_experiments -v`

Expected: missing module and aggregation-interface failures.

- [ ] **Step 3: Implement the orchestrator**

Run all `make_loco_folds(("RW9", "RW10", "RW11", "RW12"))`. Write each fold to `test_RW*/state`, `test_RW*/temperature`, and `test_RW*/lifecycle`. Aggregate each target with an unweighted four-fold mean and record the worst fold. For SOH, RUL, and temperature aggregate the corresponding baseline and `beats_baseline` flag.

- [ ] **Step 4: Protect the old baseline and make paths explicit**

Hash the configured old five-head result before and after the run and fail if hashes differ. Do not regenerate datasets inside the trainer; preparation remains an explicit upstream action. Include SHA-256 for both input CSVs in `run_config.json`.

- [ ] **Step 5: Write a concise comparison report**

The report must state five-target macro metrics, worst cells, baseline outcomes, 300-second temperature horizon, and the four-cell evidence limitation.

- [ ] **Step 6: Run and verify GREEN**

Run: `python -m unittest tests.test_train_nasa_hybrid tests.test_nasa_lifecycle_experiments -v`

Expected: all hybrid and experiment tests pass.

---

### Task 5: Render five intuitive four-cell charts

**Files:**
- Create: `src/desktop/hybrid_charts.py`
- Create: `tests/test_hybrid_charts.py`

**Interfaces:**
- Consumes: a complete hybrid run directory.
- Produces: `build_hybrid_charts(run_dir: Path) -> dict[str, Path]` with five PNG files.

- [ ] **Step 1: Write the failing chart contract test**

```python
def test_hybrid_charts_write_five_four_fold_png_files(self):
    charts = build_hybrid_charts(run_dir)
    self.assertEqual(set(charts), {"soc", "soe", "soh", "rul_cycles", "sot_5min_c"})
    self.assertTrue(all(path.is_file() for path in charts.values()))
```

Use a synthetic run fixture containing all four fold directories and prediction CSVs.

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_hybrid_charts -v`

Expected: import failure because `hybrid_charts` does not exist.

- [ ] **Step 3: Implement four-panel chart rendering**

Render a 2×2 held-out-cell grid per target. Each panel labels the cell, MAE, reference line, model line, and—where available—baseline line. The title reports macro MAE, worst-cell MAE, and a green “超过基线” or orange “未超过基线” status.

- [ ] **Step 4: Reject incomplete evidence**

Raise `ValueError` when any target or fold prediction file is missing instead of silently drawing a partial chart.

- [ ] **Step 5: Run and verify GREEN**

Run: `python -m unittest tests.test_hybrid_charts -v`

Expected: five valid PNG files and all chart tests pass.

---

### Task 6: Make the improved hybrid workflow the desktop default

**Files:**
- Modify: `src/platform/platform_core.py`
- Modify: `src/desktop/app.py`
- Modify: `tests/test_platform_core.py`
- Modify: `tests/test_desktop_app.py`

**Interfaces:**
- Consumes: `build_hybrid_command(project, settings, python_executable)` and `read_hybrid_result(run_dir)`.
- Produces: one visible project named `NASA 五状态（改进）` and a results page backed by the exact run directory created by the platform.

- [ ] **Step 1: Write failing platform tests**

```python
def test_hybrid_command_passes_platform_run_directory(self):
    command, run_dir = build_hybrid_command(project, {"stage": "smoke", "seed": 7}, Path("python"))
    self.assertIn(str(run_dir), command)
    self.assertIn("src.training.train_nasa_hybrid", command)

def test_desktop_exposes_one_improved_nasa_project(self):
    app = DesktopTrainingApp.create_for_test(project_root)
    self.assertIn("NASA 五状态（改进）", app.projects)
    self.assertNotIn("NASA 生命周期模型", app.projects)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m unittest tests.test_platform_core tests.test_desktop_app -v`

Expected: failures for missing hybrid project and command.

- [ ] **Step 3: Add platform project and command construction**

Register the improved project with the two prepared CSV paths and the hybrid trainer. Pass the platform-created `run_dir` through `--results-dir`; remove the old lifecycle project from the visible `self.projects` map without deleting stored records.

- [ ] **Step 4: Update training and result pages**

Show only `stage` and `seed` for the hybrid workflow. Read aggregate/worst/baseline fields from the completed run, show a warning card for each target that loses to its baseline, and display the five generated charts. Include a compact frozen old-baseline card without ranking incompatible splits.

- [ ] **Step 5: Run and verify GREEN**

Run: `python -m unittest tests.test_platform_core tests.test_desktop_app -v`

Expected: platform and desktop tests pass with the new default project.

---

### Task 7: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/NASA五状态数据与训练说明.md`

**Interfaces:**
- Consumes: final CLI and artifact names.
- Produces: reproducible macOS commands and a clear explanation of the new target definitions.

- [ ] **Step 1: Update documentation**

Document the three-component architecture, 300-second SOT horizon, four-fold macro evaluation, baseline warnings, smoke command, formal command, and unchanged legacy baseline.

- [ ] **Step 2: Run the entire unit-test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 3: Compile all Python sources**

Run: `python -m compileall -q src tests`

Expected: exit code 0 and no output.

- [ ] **Step 4: Run the real-data smoke experiment**

Run:

```bash
python -m src.training.train_nasa_hybrid \
  --state-data "/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/03_NASA_生命周期训练数据/nasa_state_future_samples.csv" \
  --lifecycle-data "/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/03_NASA_生命周期训练数据/nasa_lifecycle_cycles.csv" \
  --results-dir "/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/04_训练平台运行记录/01_SOC训练平台项目与运行记录/hybrid_smoke_verification" \
  --stage smoke --seed 42
```

Expected: four complete fold directories, five aggregate targets, three baseline comparisons, five charts, and unchanged old-baseline hashes.

- [ ] **Step 5: Inspect smoke metrics and charts**

Verify that no target contains NaN/Infinity, all fold counts equal four, SOT uses `sot_5min_c`, RUL predictions are not clipped to the training maximum, and every PNG opens successfully.

