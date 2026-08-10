# Generalization-First SOC Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate five-seed stability testing, six-fold leave-one-session-out validation, gated candidate selection, and one frozen A123#5 cross-cell evaluation without modifying the existing baseline artifacts.

**Architecture:** Extend the trainer with explicit, leakage-safe session splits and complete run metadata. Add a focused experiment module that creates deterministic jobs, runs each job in an immutable directory, resumes around failures, summarizes internal evidence, and only then launches one A123#5 evaluation. Keep model training, experiment orchestration, metric calculation, and desktop presentation as separate units.

**Tech Stack:** Python 3.12, PyTorch, NumPy, Pillow, standard-library `unittest`, JSON and CSV artifacts.

## Global Constraints

- A123#5 and CX2_4 must never participate in training, normalization, early stopping, scheduler decisions, or hyperparameter selection.
- Existing A123#3 baseline and A123#5 result files remain read-only; record their SHA-256 values before and after execution.
- Use seeds `11, 23, 42, 67, 101` and the approved fixed training policy from the design.
- Internal acceptance: five-seed mean MAE `<= 3.5%` and leave-one-session-out worst MAE `<= 8%`.
- Cross-cell acceptance: A123#5 MAE must not exceed the saved current result; preferred target is `<= 2.3%`.
- Every run uses a unique directory and writes no artifact into the baseline directories.
- No Optuna or new third-party dependency.
- Git is not installed on this computer. Replace commit checkpoints with a passing focused test plus `implementation_manifest.json` file hashes.

---

### Task 1: Explicit session splits and reproducible run metadata

**Files:**
- Modify: `src/training/train_lstm.py`
- Modify: `tests/test_train_lstm_cli.py`

**Interfaces:**
- Consumes: ordered session names loaded by `load_sessions()`.
- Produces: `resolve_session_split(available, requested_train, requested_validation, requested_test) -> tuple[list[str], str, str]` and CLI options `--train-sessions`, `--validation-session`, `--test-session`.
- Produces: `run_config.json` beside every completed model.

- [ ] **Step 1: Write failing split tests**

Add tests with these assertions:

```python
def test_explicit_session_split_is_disjoint_and_preserves_order(self):
    split = train_lstm.resolve_session_split(
        ["a", "b", "c", "d"], ["c", "a"], "b", "d"
    )
    self.assertEqual(split, (["c", "a"], "b", "d"))

def test_explicit_session_split_rejects_overlap_and_unknown_names(self):
    with self.assertRaisesRegex(ValueError, "overlap"):
        train_lstm.resolve_session_split(["a", "b", "c"], ["a"], "a", "c")
    with self.assertRaisesRegex(ValueError, "unknown"):
        train_lstm.resolve_session_split(["a", "b", "c"], ["a"], "b", "x")
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_train_lstm_cli -v
```

Expected: FAIL because `resolve_session_split` does not exist.

- [ ] **Step 3: Implement explicit split resolution**

Add this behavior:

```python
def resolve_session_split(available, requested_train=None, requested_validation=None, requested_test=None):
    if requested_train is None and requested_validation is None and requested_test is None:
        return list(available[:-2]), available[-2], available[-1]
    if not requested_train or not requested_validation or not requested_test:
        raise ValueError("Explicit split requires train, validation, and test sessions.")
    selected = list(requested_train) + [requested_validation, requested_test]
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise ValueError(f"Explicit split contains unknown sessions: {unknown}")
    if len(selected) != len(set(selected)):
        raise ValueError("Explicit split contains overlap between train/validation/test.")
    return list(requested_train), requested_validation, requested_test
```

Use `nargs="+"` for `--train-sessions`. Preserve the old `names[:-2], names[-2], names[-1]` behavior when no explicit split is supplied.

- [ ] **Step 4: Write and verify run metadata**

Extend the existing subprocess training test to assert `run_config.json` contains:

```python
{
    "data_path": str(data.resolve()),
    "train_sessions": ["a"],
    "validation_session": "b",
    "test_session": "c",
    "window_steps": 2,
    "seed": 7,
    "training_policy": {
        "hidden_size": 4,
        "dropout": 0.1,
        "optimizer": "AdamW",
    },
}
```

Write the actual configuration from parsed arguments; do not hard-code test values.

- [ ] **Step 5: Run focused tests and record hashes**

Run the Task 1 test command and require `OK`. Record modified-file SHA-256 values in the later implementation manifest.

### Task 2: Reusable SOC-band analysis

**Files:**
- Modify: `src/evaluation/analyze_predictions.py`
- Modify: `tests/test_train_lstm_cli.py`
- Create: `tests/test_analyze_predictions.py`

**Interfaces:**
- Produces: `analyze_predictions(path: Path) -> dict[str, dict[str, float | int | None]]` and `write_analysis(predictions: Path, output: Path) -> dict`.
- Consumes: `test_predictions.csv` with `reference_soc,predicted_soc` columns.

- [ ] **Step 1: Write a failing metric test**

Create a CSV covering all five SOC bands and assert exact counts and MAE:

```python
report = analyze_predictions(predictions)
self.assertEqual(report["0-20%"]["count"], 1)
self.assertAlmostEqual(report["0-20%"]["MAE_pct"], 1.0, places=6)
```

Also test an empty band returns `MAE_pct=None` and `bias_pct=None`, not `NaN`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
..\..\work\soc_venv\Scripts\python.exe -m unittest tests.test_analyze_predictions -v
```

Expected: FAIL because the reusable functions do not exist.

- [ ] **Step 3: Extract the reusable functions**

Move the existing calculation out of `main()` without changing CLI behavior. For an empty band, write:

```python
{"count": 0, "MAE_pct": None, "bias_pct": None}
```

- [ ] **Step 4: Make every training run write band metrics**

After `test_predictions.csv` is closed in `train_lstm.py`, call `write_analysis()` to create `metrics_by_soc.json`. Extend the existing real subprocess test to require the file.

- [ ] **Step 5: Run Task 2 tests**

Run both test modules and require `OK`.

### Task 3: Deterministic experiment job planning and leakage guards

**Files:**
- Create: `src/evaluation/generalization_experiments.py`
- Create: `tests/test_generalization_experiments.py`

**Interfaces:**
- Produces immutable `ExperimentJob` with fields `job_id`, `stage`, `seed`, `train_sessions`, `validation_session`, `test_session`, and `results_dir`.
- Produces `make_seed_jobs(sessions, root) -> list[ExperimentJob]` and `make_loso_jobs(sessions, root, seed) -> list[ExperimentJob]`.
- Produces `assert_a1233_only(job)`.

- [ ] **Step 1: Write failing deterministic-plan tests**

Assert:

```python
jobs = make_seed_jobs(SESSIONS, root)
self.assertEqual([job.seed for job in jobs], [11, 23, 42, 67, 101])
self.assertEqual(len({job.job_id for job in jobs}), 5)

folds = make_loso_jobs(SESSIONS, root, seed=42)
self.assertEqual(len(folds), 6)
self.assertEqual({job.test_session for job in folds}, set(SESSIONS))
for job in folds:
    self.assertNotIn(job.test_session, job.train_sessions)
    self.assertNotEqual(job.validation_session, job.test_session)
```

Add rejection tests for any session beginning with `A123#5` or any overlap.

- [ ] **Step 2: Verify RED**

Run the new test module and expect import failure.

- [ ] **Step 3: Implement job creation**

Use sorted session names. For LOSO fold `i`, choose test `sessions[i]`, validation `sessions[(i - 1) % len(sessions)]`, and all remaining sessions for training. Job IDs must be stable, such as `seed-011` and `loso-01-A123_3_05_28_13` after filename-safe normalization.

- [ ] **Step 4: Implement input checks**

Require exactly six A123#3 sessions for the formal plan, unique session names, and no `A123#5`/`CX2` prefix. Return clear `ValueError` messages before creating directories.

- [ ] **Step 5: Run Task 3 tests**

Require all new tests to pass.

### Task 4: Safe run execution, resume, and baseline protection

**Files:**
- Modify: `src/evaluation/generalization_experiments.py`
- Modify: `src/project_paths.py`
- Modify: `tests/test_generalization_experiments.py`
- Modify: `tests/test_project_paths.py`

**Interfaces:**
- Adds `DataCenterPaths.generalization_results_dir` and `DataCenterPaths.a1235_processed_csv`.
- Produces `sha256_files(paths) -> dict[str, str]`, `verify_required_artifacts(run_dir)`, and `run_job(job, python_executable, data_path, project_root) -> dict`.

- [ ] **Step 1: Write failing path and protection tests**

Assert the two paths resolve to:

```text
03_模型与实验结果/03_综合泛化验证
05_外部评估数据/03_外部数据清单与处理结果/cross_cell_a123_5_part1/a123_5_soc_30s.csv
```

Test that `sha256_files()` detects a changed baseline file.

- [ ] **Step 2: Write failing run-state tests**

Use a temporary fake trainer process to assert:

- a new directory starts with `status.json` state `running`;
- success requires all nine artifacts from the design;
- a failed subprocess records `failed` and its return code;
- a valid `succeeded` job is skipped on resume;
- an incomplete directory is not treated as succeeded;
- an existing nonempty unrecognized directory is never overwritten.

- [ ] **Step 3: Verify RED**

Run Tasks 3 and 4 test modules; expect missing interfaces.

- [ ] **Step 4: Implement the safe runner**

Build a fixed command using `sys.executable -m src.training.train_lstm` and explicit split arguments. Add approved policy arguments verbatim. Capture stdout/stderr into `run.log`. After training, call `ensure_run_charts()` and require:

```python
REQUIRED = {
    "metrics.json", "metrics_by_soc.json", "training_history.json",
    "test_predictions.csv", "soc_prediction.png", "validation_loss.png",
    "lstm_soc.pt", "run_config.json", "run.log",
}
```

Use `shutil.disk_usage(results_root).free >= 2 * 1024**3` before formal execution. Store state transitions atomically through a temporary JSON file followed by `Path.replace()`.

- [ ] **Step 5: Verify runner tests**

Run focused tests and require `OK`.

### Task 5: Statistical summaries and internal acceptance gate

**Files:**
- Modify: `src/evaluation/generalization_experiments.py`
- Modify: `tests/test_generalization_experiments.py`

**Interfaces:**
- Produces `summarize_stage(run_dirs) -> dict` and `evaluate_internal_gate(seed_summary, loso_summary) -> dict`.
- Writes `seed_summary.json`, `loso_summary.json`, and `internal_gate.json`.

- [ ] **Step 1: Write failing summary tests**

Create three succeeded fake runs and one failed run. Assert only succeeded runs contribute and summary includes `count`, `mean`, `median`, `standard_deviation`, `minimum`, `maximum`, and `worst_job_id` for MAE/RMSE.

Test exact gate boundaries:

```python
self.assertTrue(evaluate_internal_gate({"MAE_pct": {"mean": 3.5}}, {"MAE_pct": {"maximum": 8.0}})["passed"])
self.assertFalse(evaluate_internal_gate({"MAE_pct": {"mean": 3.5001}}, {"MAE_pct": {"maximum": 8.0}})["passed"])
```

- [ ] **Step 2: Verify RED**

Run the experiment tests and expect missing summary functions.

- [ ] **Step 3: Implement summaries**

Use `statistics.mean`, `statistics.median`, and population standard deviation. Require all five seed runs and all six LOSO runs; otherwise set gate state to `incomplete`, not failed.

- [ ] **Step 4: Select the median seed deterministically**

Select the seed run with MAE closest to the five-run median; break ties by lower seed number. Write the selection and reason into `internal_gate.json`.

- [ ] **Step 5: Run Task 5 tests**

Require focused tests to pass.

### Task 6: Candidate retraining and one-time A123#5 gate

**Files:**
- Modify: `src/evaluation/generalization_experiments.py`
- Modify: `tests/test_generalization_experiments.py`
- Modify: `src/evaluation/evaluate_external_cell.py`
- Modify: `tests/test_evaluate_external_cell.py`

**Interfaces:**
- Produces `run_candidate_and_cross_cell(...) -> dict`.
- Writes `candidate/`, `cross_cell_candidate/`, and `final_decision.json` under the generalization experiment root.

- [ ] **Step 1: Write failing gate tests**

Assert cross-cell evaluation is not called when `internal_gate.passed` is false or incomplete. When true, assert it receives only the frozen candidate model and A123#5 processed CSV.

Test `evaluate_external_cell` rejects an output directory equal to the saved baseline or saved cross-cell result directory.

- [ ] **Step 2: Verify RED**

Run the experiment and external-evaluator tests; expect missing gate behavior.

- [ ] **Step 3: Implement candidate retraining**

Run one candidate with the median seed and the fixed baseline split. Freeze its `lstm_soc.pt` and `run_config.json`; compute hashes before cross-cell evaluation.

- [ ] **Step 4: Implement the cross-cell decision**

Load the saved current A123#5 MAE from `DataCenterPaths.cross_cell_results_dir / "metrics.json"`. Classify the candidate as:

```python
if candidate_mae <= 2.3:
    decision = "preferred_target_met"
elif candidate_mae <= current_mae:
    decision = "non_degrading_candidate"
else:
    decision = "keep_existing_baseline"
```

Always state that the metric uses the Coulomb-counting reference label and the currently processed A123#5 session scope.

- [ ] **Step 5: Run Task 6 tests**

Require focused tests to pass and verify no baseline file changed.

### Task 7: CLI, report, and desktop summary presentation

**Files:**
- Modify: `src/evaluation/generalization_experiments.py`
- Modify: `src/platform/platform_core.py`
- Modify: `src/desktop/app.py`
- Modify: `tests/test_platform_core.py`
- Modify: `tests/test_desktop_app.py`
- Modify: `README.md`
- Modify: `docs/OPTIMIZATION_PLAN.md`

**Interfaces:**
- CLI modes: `--stage smoke`, `--stage internal`, `--stage cross-cell`, and `--stage all`.
- Produces `generalization_summary.json`, `generalization_summary.csv`, and `综合泛化验证报告.md`.
- Produces `read_generalization_summary(path: Path) -> dict` for the desktop application.

- [ ] **Step 1: Write failing CLI/report tests**

Assert `--help` lists all four stages. Feed fixed summaries into `write_report()` and assert the report contains all acceptance thresholds, seed statistics, six LOSO rows, A123#5 decision, label caveat, and exact session scope.

- [ ] **Step 2: Write failing desktop-read tests**

Assert `read_generalization_summary()` rejects missing required fields and returns a validated summary for a complete artifact. Assert the desktop result page references the generalization summary and does not allow it to overwrite individual run results.

- [ ] **Step 3: Verify RED**

Run experiment, platform, and desktop tests; expect missing interfaces.

- [ ] **Step 4: Implement CLI and report output**

`smoke` creates the same job graph with one epoch and caps of 1,000/500/500. `internal` runs seeds plus LOSO. `cross-cell` requires an already-passed `internal_gate.json`. `all` runs internal and conditionally continues. The report begins with the decision, followed by evidence tables and limitations.

- [ ] **Step 5: Implement read-only desktop summary**

Add a summary card to the results page showing seed mean MAE, LOSO worst MAE, A123#5 MAE, and decision. The card reads artifacts only; it cannot trigger experiments or modify results.

- [ ] **Step 6: Update beginner documentation**

Document the exact command:

```powershell
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage all
```

Explain the four stages and why A123#5 is evaluated only after internal selection.

- [ ] **Step 7: Run Task 7 tests**

Require all focused tests to pass.

### Task 8: Full verification and formal experiment execution

**Files:**
- Create through the runner: `implementation_manifest.json`
- Create through the runner: all experiment artifacts under `DataCenterPaths.generalization_results_dir`

**Interfaces:**
- Consumes the completed implementation and approved data.
- Produces verified experiment evidence and a final decision without replacing the baseline.

- [ ] **Step 1: Run the complete test suite**

```powershell
..\..\work\soc_venv\Scripts\python.exe -m unittest discover -s tests -v
..\..\work\soc_venv\Scripts\python.exe -m py_compile src\training\train_lstm.py src\evaluation\generalization_experiments.py src\evaluation\evaluate_external_cell.py src\platform\platform_core.py src\desktop\app.py
```

Expected: zero failures and zero compile errors.

- [ ] **Step 2: Run a smoke workflow**

```powershell
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage smoke
```

Expected: seed and LOSO job planning, isolated one-epoch artifacts, summaries, no baseline hash changes, and no A123#5 training use.

- [ ] **Step 3: Inspect smoke charts and manifests**

Open one prediction chart and one training/validation chart at original resolution. Verify every required artifact and compare baseline hashes.

- [ ] **Step 4: Run the formal internal workflow**

```powershell
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage internal
```

Expected: five seed runs, six LOSO runs, complete summaries, and an explicit internal gate result.

- [ ] **Step 5: Run the gated cross-cell stage**

If and only if the internal gate passed:

```powershell
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage cross-cell
```

Expected: one frozen candidate evaluation and `final_decision.json`. If the internal gate did not pass, report the failing criterion and do not run A123#5.

- [ ] **Step 6: Create the implementation manifest**

Write the SHA-256 of modified code, test files, baseline artifacts before/after, the test count, Python/PyTorch versions, experiment root, completed job count, and final decision. Verify baseline before/after hashes are identical.

- [ ] **Step 7: Final evidence review**

Check the design line by line. Report actual seed mean, LOSO worst MAE, A123#5 MAE, whether 2.3% was reached, failed/incomplete jobs, label limitations, and whether the existing baseline was retained.
