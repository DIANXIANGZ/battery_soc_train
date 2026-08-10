# XGBoost / PyTorch OpenMP crash evidence

## Observed failure

- Process exit: `SIGSEGV` / exit code 139.
- Native stack location: XGBoost `XGQuantileDMatrixCreateFromCallback` and OpenMP `__kmp_*` frames.
- Reproduction boundary: importing/using PyTorch and then fitting XGBoost in the same Python process.
- Control result: XGBoost fitting in a clean Python 3.12 interpreter without importing PyTorch completed normally.

The four preserved macOS crash reports are:

- `Python-2026-08-03-181434.ips` (`18:14:25 +0800`)
- `Python-2026-08-03-181531.ips` (`18:15:30 +0800`)
- `Python-2026-08-03-181554.ips` (`18:15:53 +0800`)
- `Python-2026-08-03-181617.ips` (`18:16:16 +0800`)

Every report contains `libtorch_python`, `libtorch`, `libtorch_cpu`, `libc10`, and three `libomp` images with distinct UUIDs: `e56febf1-...`, `e3a31ab3-...`, and `e08eca60-...`.

## Root cause assessment

The crashing process loaded the PyTorch native libraries and incompatible OpenMP runtime instances. The failure is below Python exception handling, so retries or Python-level error handling cannot make the in-process route safe.

## Enforced mitigation

`src.training.train_custom` runs the XGBoost fit in a dedicated subprocess through `src.training.xgboost_backend`. The backend contains no top-level PyTorch import and aborts if `torch` is already present in its module table. It uses XGBoost's native `DMatrix`/`train` interface and deliberately disables the optional sklearn integration, avoiding sklearn's bundled OpenMP runtime. Multi-target regression is implemented as one native booster per target. Training arrays and predictions cross the process boundary through a temporary directory that is removed after completion.

## Safe isolated verification

Four independent controls were run with global `/opt/homebrew/bin/python3.12`, an empty environment (`env -i`), isolated interpreter mode, `OMP_NUM_THREADS=1`, and no Torch import. All four native `hist` fits completed with finite predictions. A native-XGBoost-only control reported:

- `torch_loaded: false`
- `sklearn_loaded: false`
- one OpenMP runtime: `/opt/homebrew/Cellar/libomp/22.1.8/lib/libomp.dylib`

The automated backend regression plus the custom-training integration tests pass (`4 passed`).

The unsafe same-process PyTorch/XGBoost fitting path must not be restored unless the native runtime conflict is independently resolved and validated.
