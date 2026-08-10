#!/usr/bin/env bash
# Set up a fresh macOS Python environment without reusing a Windows virtualenv.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT=""
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv-macos}"

usage() {
  echo "Usage: bash scripts/macos_setup.sh --data-root /absolute/path/to/SOC-data-center"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-root) DATA_ROOT="${2:-}"; shift 2 ;;
    --python) PYTHON_BIN="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$DATA_ROOT" ]] || { echo "--data-root is required; no Windows data path will be guessed." >&2; exit 2; }
[[ "$DATA_ROOT" = /* ]] || { echo "--data-root must be an absolute macOS path." >&2; exit 2; }
[[ -d "$DATA_ROOT" ]] || { echo "Data center does not exist: $DATA_ROOT" >&2; exit 2; }
command -v "$PYTHON_BIN" >/dev/null || { echo "Python not found: $PYTHON_BIN. Install Python 3.12, then retry." >&2; exit 2; }
"$PYTHON_BIN" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' || {
  echo "This project is pinned for Python 3.12." >&2; exit 2;
}

cd "$PROJECT_ROOT"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r requirements.txt
"$VENV_DIR/bin/python" - "$DATA_ROOT" <<'PY'
from pathlib import Path
import sys
from src.project_paths import DataCenterPaths, DEFAULT_CONFIG_PATH

root = Path(sys.argv[1]).resolve()
DataCenterPaths.save_config(DEFAULT_CONFIG_PATH, root)
print(f"Configured data center: {root}")
PY
"$VENV_DIR/bin/python" -m src.training.verify_pytorch
echo "Setup complete. Next run: bash scripts/macos_verify.sh"
