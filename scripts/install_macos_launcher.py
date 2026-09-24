#!/usr/bin/env python3
"""Install the reproducible macOS launcher for the desktop training platform.

The installer only packages the desktop entry point. It never copies data,
models, or training results and never starts Python during installation.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


BUNDLE_NAME = "SOC电池训练平台.app"
BUNDLE_ID = "com.wanghaoming.soc-training-platform"
BUNDLE_EXECUTABLE = "SOCTrainingPlatformLauncher"
DEFAULT_PROJECT_ROOT = Path(
    "/Users/wanghaoming/Public/battery_soc_project/.worktrees/training-platform-four-targets-20260923"
)
SUMMARY_RELATIVE_PATH = Path("docs/audits/2026-09-23-non-rul-four-target-completion.json")
ICON_RELATIVE_PATH = Path("assets/macos/soc-training-platform-icon.png")
DEFAULT_ICON_SOURCE = Path(__file__).resolve().parents[1] / ICON_RELATIVE_PATH
DEFAULT_PYTHON_CANDIDATES = (
    Path("/opt/homebrew/bin/python3.12"),
    Path("/usr/local/bin/python3.12"),
    Path("/usr/bin/python3.12"),
)
CODE_SIGN = Path("/usr/bin/codesign")


def _python_is_usable(path: Path, project_root: Path = DEFAULT_PROJECT_ROOT) -> bool:
    """Require an executable Python 3.12 with the desktop import available."""

    if not path.is_file() or not os.access(path, os.X_OK):
        return False
    probe = (
        "import sys; assert sys.version_info[:2] == (3, 12); "
        "import tkinter; import src.desktop.app"
    )
    try:
        result = subprocess.run(
            [str(path), "-c", probe],
            cwd=str(project_root),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def resolve_python(candidates: Iterable[Path] | None = None, project_root: Path = DEFAULT_PROJECT_ROOT) -> Path:
    """Return the first usable, explicitly allowed Python 3.12 candidate."""

    values = tuple(candidates or DEFAULT_PYTHON_CANDIDATES)
    checked: list[str] = []
    for candidate in values:
        path = Path(candidate).expanduser()
        checked.append(str(path))
        if _python_is_usable(path, project_root):
            return path.resolve()
    raise RuntimeError("未找到可用的 Python 3.12（需要 tkinter 和 src.desktop.app）。已检查：" + ", ".join(checked))


def validate_project_root(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    app_path = root / "src" / "desktop" / "app.py"
    summary_path = root / SUMMARY_RELATIVE_PATH
    if not app_path.is_file():
        raise RuntimeError(f"固定项目根缺少 src/desktop/app.py：{root}")
    if not summary_path.is_file():
        raise RuntimeError(f"固定项目根缺少四目标摘要：{summary_path}")
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError(f"四目标摘要无法读取：{summary_path}") from error
    if not isinstance(payload, dict) or payload.get("status") != "COMPLETE_FOUR_TARGET_SCOPED_BASELINES":
        raise RuntimeError(f"四目标摘要状态无效：{summary_path}")
    if not isinstance(payload.get("targets"), dict) or set(payload["targets"]) != {"soc", "system_soe", "soh", "sot"}:
        raise RuntimeError(f"四目标摘要缺少目标条目：{summary_path}")
    return root


def _validate_icon_source(icon_source: Path) -> Path:
    source = Path(icon_source).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"图标源不存在：{source}")
    if source.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"图标源不是有效PNG：{source}")
    return source


def _make_icns(icon_source: Path, destination: Path, work_dir: Path) -> None:
    iconset = work_dir / "SOCTrainingPlatformIcon.iconset"
    iconset.mkdir(parents=True)
    sizes = (16, 32, 128, 256, 512, 1024)
    for size in sizes:
        output = iconset / f"icon_{size}x{size}.png"
        try:
            subprocess.run(
                ["/usr/bin/sips", "-z", str(size), str(size), str(icon_source), "--out", str(output)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise RuntimeError("无法使用 macOS sips 生成图标尺寸") from error
    try:
        subprocess.run(
            ["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(destination)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("无法使用 macOS iconutil 生成 icns") from error
    finally:
        shutil.rmtree(iconset, ignore_errors=True)


def _launcher_text(project_root: Path, python_path: Path) -> str:
    project_literal = shlex.quote(str(project_root))
    python_literal = shlex.quote(str(python_path))
    app_path = shlex.quote(str(project_root / "src" / "desktop" / "app.py"))
    summary_path = shlex.quote(str(project_root / SUMMARY_RELATIVE_PATH))
    return f"""#!/bin/zsh
set -u

PROJECT_ROOT={project_literal}
PYTHON_BIN={python_literal}
APP_PATH={app_path}
SUMMARY_PATH={summary_path}
LOG_DIR="$HOME/Library/Logs/SOCBatteryTrainingPlatform"
LOG_FILE="$LOG_DIR/launcher.log"

show_failure() {{
    local message="$1"
    /usr/bin/osascript -e "display alert \\\"SOC电池训练平台无法启动\\\" message \\\"$message\\\" as critical" >/dev/null 2>&1 || true
}}

if ! /bin/mkdir -p "$LOG_DIR"; then
    show_failure "无法创建启动日志目录。"
    exit 1
fi
{{
    /bin/echo "[$(/bin/date -u +%Y-%m-%dT%H:%M:%SZ)] launcher start"
    /bin/echo "project=$PROJECT_ROOT"
}} >>"$LOG_FILE" 2>&1

if [[ ! -d "$PROJECT_ROOT" || ! -f "$APP_PATH" || ! -f "$SUMMARY_PATH" ]]; then
    /bin/echo "固定项目根或四目标摘要不存在。" >>"$LOG_FILE"
    show_failure "固定项目根或四目标摘要不存在。"
    exit 1
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
    /bin/echo "Python解释器不存在或不可执行：$PYTHON_BIN" >>"$LOG_FILE"
    show_failure "已验证的 Python 3.12 不可用。"
    exit 1
fi
cd "$PROJECT_ROOT" || {{ show_failure "无法进入固定项目根。"; exit 1; }}
if ! "$PYTHON_BIN" -c 'import sys; assert sys.version_info[:2] == (3, 12); import tkinter; import src.desktop.app' >>"$LOG_FILE" 2>&1; then
    /bin/echo "Python 或桌面模块预检失败。" >>"$LOG_FILE"
    show_failure "Python 或桌面模块预检失败。请查看启动日志。"
    exit 1
fi
"$PYTHON_BIN" -m src.desktop.app >>"$LOG_FILE" 2>&1
status=$?
if [[ "$status" -ne 0 ]]; then
    /bin/echo "desktop app exited with status $status" >>"$LOG_FILE"
    show_failure "平台启动失败（退出码 $status）。请查看启动日志。"
fi
exit "$status"
"""


def _write_info_plist(path: Path) -> None:
    payload = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": "SOC电池训练平台",
        "CFBundleExecutable": BUNDLE_EXECUTABLE,
        "CFBundleIconFile": "SOCTrainingPlatformIcon.icns",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "SOC电池训练平台",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    path.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True))


def build_bundle(project_root: Path, destination: Path, icon_source: Path, python_path: Path) -> Path:
    """Create a complete bundle at a new destination without starting it."""

    root = validate_project_root(project_root)
    source = _validate_icon_source(icon_source)
    python = Path(python_path).expanduser().resolve()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError(f"Python解释器不存在或不可执行：{python}")
    bundle = Path(destination).expanduser().resolve()
    if bundle.exists():
        raise RuntimeError(f"临时目标已存在，拒绝覆盖：{bundle}")
    contents = bundle / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)
    _write_info_plist(contents / "Info.plist")
    shutil.copy2(source, resources / "soc-training-platform-icon.png")
    _make_icns(source, resources / "SOCTrainingPlatformIcon.icns", resources)
    launcher = macos / BUNDLE_EXECUTABLE
    launcher.write_text(_launcher_text(root, python), encoding="utf-8")
    launcher.chmod(0o755)
    return bundle


def _existing_bundle_is_owned(destination: Path) -> bool:
    if destination.is_symlink() or not destination.is_dir():
        raise RuntimeError(f"桌面目标不是可识别的app bundle，拒绝覆盖：{destination}")
    info_path = destination / "Contents" / "Info.plist"
    if not info_path.is_file():
        raise RuntimeError(f"同名app缺少Info.plist，拒绝覆盖：{destination}")
    try:
        payload = plistlib.loads(info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise RuntimeError(f"同名app的Info.plist无法读取，拒绝覆盖：{destination}") from error
    if payload.get("CFBundleIdentifier") != BUNDLE_ID:
        raise RuntimeError(f"发现不同bundle id的同名app，拒绝覆盖：{destination}")
    return True


def _try_ad_hoc_sign(bundle: Path) -> bool:
    """Attempt an ad-hoc signature; never claim success when codesign fails."""

    if not CODE_SIGN.is_file() or not os.access(CODE_SIGN, os.X_OK):
        print("警告：未找到 codesign，bundle 保持未签名。", file=sys.stderr)
        return False
    try:
        subprocess.run(
            [str(CODE_SIGN), "--force", "--deep", "--sign", "-", str(bundle)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"警告：ad-hoc codesign 失败，bundle 保持未签名：{error}", file=sys.stderr)
        return False
    return True


def install_bundle(
    project_root: Path,
    desktop_dir: Path,
    icon_source: Path,
    python_path: Path,
) -> Path:
    """Stage then install one owned bundle; repeated installs replace only it."""

    root = validate_project_root(project_root)
    python = Path(python_path).expanduser().resolve()
    if not _python_is_usable(python, root):
        raise RuntimeError(f"Python解释器或桌面模块预检失败：{python}")
    desktop = Path(desktop_dir).expanduser().resolve()
    desktop.mkdir(parents=True, exist_ok=True)
    destination = desktop / BUNDLE_NAME
    if destination.exists():
        _existing_bundle_is_owned(destination)
    staging = Path(tempfile.mkdtemp(prefix=".soc-training-platform-", dir=str(desktop)))
    try:
        staged_bundle = build_bundle(root, staging / BUNDLE_NAME, icon_source, python)
        _try_ad_hoc_sign(staged_bundle)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staged_bundle, destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return destination


def _show_installer_failure(message: str) -> None:
    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["/usr/bin/osascript", "-e", f'display alert "SOC电池训练平台安装失败" message "{message}" as critical'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the SOC battery training platform macOS launcher")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--desktop-dir", type=Path, default=Path.home() / "Desktop")
    parser.add_argument("--icon-source", type=Path, default=DEFAULT_ICON_SOURCE)
    parser.add_argument("--python", dest="python_path", type=Path)
    args = parser.parse_args(argv)
    try:
        python_path = args.python_path.expanduser().resolve() if args.python_path else resolve_python(project_root=args.project_root)
        destination = install_bundle(args.project_root, args.desktop_dir, args.icon_source, python_path)
    except (OSError, RuntimeError) as error:
        print(f"安装失败：{error}", file=sys.stderr)
        _show_installer_failure(str(error))
        return 2
    print(f"已安装：{destination}")
    print(f"Bundle ID：{BUNDLE_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
