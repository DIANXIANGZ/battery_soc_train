#!/usr/bin/env bash
# Verify the transferred project on macOS. This does not train or alter datasets.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv-macos}"
PYTHON="$VENV_DIR/bin/python"

[[ -x "$PYTHON" ]] || { echo "Mac virtual environment not found: $PYTHON" >&2; exit 2; }
cd "$PROJECT_ROOT"
"$PYTHON" - <<'PY'
from src.project_paths import DataCenterPaths
import torch

paths = DataCenterPaths.from_config()
if not paths.root.is_dir():
    raise SystemExit(f"Configured data center is missing: {paths.root}")
print(f"Python data center: {paths.root}")
print(f"PyTorch: {torch.__version__}")
PY
"$PYTHON" -m unittest discover -s tests -p 'test_*.py' -v
echo "MACOS_TRANSFER_VERIFIED"
