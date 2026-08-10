# Lightweight Windows Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify `dist/installer/SOC电池训练平台安装程序.exe`, a lightweight per-user Windows installer that creates an isolated runtime and never packages or deletes external SOC data.

**Architecture:** PyInstaller builds the Tkinter UI as a standalone windowed executable while excluding training-only libraries. Inno Setup copies that GUI and the platform training source, then invokes a hidden PowerShell bootstrap that extracts a registration-free CPython NuGet runtime under `{app}\runtime\python`, installs pinned packages, verifies PyTorch, and writes a durable log.

**Tech Stack:** Python 3.12, PowerShell 5.1+, Inno Setup 6, Tkinter, pip, CPU PyTorch, `unittest`.

## Global Constraints

- Target 64-bit Windows 10 and Windows 11.
- Use the official CPython 3.12.10 NuGet package from `https://www.nuget.org/api/v2/package/python/3.12.10`; require SHA-256 `0EB85C2DFCCCCF1B17352DE4C397F69194035B7D37149EACC16F1147D93DE3B8` before compiling the setup package.
- Do not call global `python`, `pip`, or `py` during application startup or training.
- Do not add Python to `PATH`, install a Python launcher, or associate Python files.
- Do not package the current `configs/paths.json`, datasets, models, experiment results, `.venv`, or `.idea`.
- Installation and uninstallation must not modify or remove the external data center.
- Final artifact: `dist/installer/SOC电池训练平台安装程序.exe` with measured size and SHA-256.

---

### Task 1: Installed-runtime resolution

**Files:**
- Modify: `src/platform/platform_core.py`
- Modify: `tests/test_platform_core.py`

**Interfaces:**
- Consumes: `project_root: Path`.
- Produces: `resolve_training_python(project_root: Path) -> Path`, preferring `<project_root>/runtime/python/python.exe` before the development workspace runtime.

- [ ] **Step 1: Write a failing private-runtime test**

Create a temporary installed-project layout containing `runtime/python/python.exe` and a separate development-style `work/soc_venv/Scripts/python.exe`. Assert that `resolve_training_python` returns the private installed interpreter.

- [ ] **Step 2: Run the test and verify RED**

```powershell
& '..\..\work\soc_venv\Scripts\python.exe' -B -m unittest tests.test_platform_core.PlatformStoreTests.test_installed_private_runtime_has_priority -v
```

Expected: failure because the current resolver only checks the development workspace runtime.

- [ ] **Step 3: Implement the smallest resolver change**

Check `<project_root>/runtime/python/python.exe` first. Preserve the current development fallback and the existing `FileNotFoundError` behavior.

- [ ] **Step 4: Run platform-core tests and verify GREEN**

```powershell
& '..\..\work\soc_venv\Scripts\python.exe' -B -m unittest tests.test_platform_core -v
```

Expected: `OK`.

### Task 2: Runtime bootstrap and packaging contract

**Files:**
- Create: `installer/setup_runtime.ps1`
- Create: `installer/installer_requirements.txt`
- Create: `tests/test_installer_packaging.py`

**Interfaces:**
- Consumes: `-InstallRoot`, `-PythonPackage`, and the copied application tree.
- Produces: `<InstallRoot>/runtime/python/python.exe`, `<InstallRoot>/runtime/python/pythonw.exe`, `<InstallRoot>/logs/install-runtime.log`, and exit code `0` only after verification succeeds.

- [ ] **Step 1: Write failing packaging-contract tests**

Assert that the bootstrap:

- accepts explicit install-root and Python-installer paths;
- invokes the official installer with `InstallAllUsers=0`, `PrependPath=0`, `Include_launcher=0`, `AssociateFiles=0`, and an explicit private `TargetDir`;
- installs packages only through the private interpreter;
- runs `-m src.training.verify_pytorch` through that interpreter;
- writes a log below the installed root;
- never references the current data-center path or global `py`/`pip` commands.

Assert that `installer_requirements.txt` contains the same four pinned runtime dependencies as `requirements.txt`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
& '..\..\work\soc_venv\Scripts\python.exe' -B -m unittest tests.test_installer_packaging -v
```

Expected: failure because installer files do not exist.

- [ ] **Step 3: Implement the hidden bootstrap**

Use strict PowerShell error handling, UTF-8 logging, explicit process exit-code checks, and quoted argument arrays. Extract the CPython 3.12.10 NuGet `tools` runtime into `runtime\python`, bootstrap and upgrade pip, install `installer_requirements.txt`, and run the verification module from the application working directory.

- [ ] **Step 4: Run packaging-contract tests and verify GREEN**

Run the Task 2 test command and expect `OK`.

### Task 3: Inno Setup source and reproducible build script

**Files:**
- Create: `installer/SOCTrainingLab.iss`
- Create: `scripts/build_installer.ps1`
- Modify: `tests/test_installer_packaging.py`

**Interfaces:**
- Consumes: source tree, official CPython 3.12 NuGet package, PyInstaller, and Inno Setup `ISCC.exe`.
- Produces: `dist/installer/SOC电池训练平台安装程序.exe`.

- [ ] **Step 1: Add failing installer-manifest tests**

Assert that the Inno script:

- is per-user and 64-bit;
- allows directory selection;
- excludes `.venv`, `.idea`, tests, build output, current `configs/paths.json`, and all data/results;
- creates an empty writable `configs` directory;
- runs `setup_runtime.ps1` hidden and checks its exit code;
- creates optional desktop and mandatory Start Menu shortcuts using the packaged GUI executable;
- registers uninstall without deleting any path outside `{app}`;
- names the output exactly `SOC电池训练平台安装程序.exe`.

Assert that the build script builds the GUI with pinned PyInstaller while excluding PyTorch, locates or installs Inno Setup, downloads and verifies the pinned official CPython NuGet runtime, invokes `ISCC.exe`, and verifies the final artifact.

- [ ] **Step 2: Run tests and verify RED**

Run `tests.test_installer_packaging` and expect missing-manifest/build-script failures.

- [ ] **Step 3: Implement Inno manifest and build script**

Use a fixed `AppId`, `PrivilegesRequired=lowest`, `ArchitecturesAllowed=x64compatible`, LZMA2 compression, and `[UninstallDelete]` entries restricted to `{app}`. The build script places downloaded tools and CPython under a disposable build-cache directory, never under the external data center.

- [ ] **Step 4: Run packaging-contract tests and verify GREEN**

Run `tests.test_installer_packaging` and expect `OK`.

### Task 4: Build, install-smoke-test, and handoff

**Files:**
- Generate: `dist/installer/SOC电池训练平台安装程序.exe`
- Generate: `dist/installer/SHA256.txt`
- Verify: installed application in a disposable directory outside the source tree.

**Interfaces:**
- Consumes: Tasks 1–3 and an internet connection.
- Produces: tested installer artifact and verification evidence.

- [ ] **Step 1: Run the full project test suite**

```powershell
& '..\..\work\soc_venv\Scripts\python.exe' -B -m unittest discover -s tests -q
```

Expected: exit code `0` and `OK`.

- [ ] **Step 2: Build the installer**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

Expected: exit code `0` and the exact final EXE path.

- [ ] **Step 3: Perform a disposable silent installation**

Install to a disposable directory on a drive with sufficient free space. Do not reuse the development runtime. Wait for setup to finish and require setup exit code `0`.

- [ ] **Step 4: Verify the installed private runtime**

From the disposable installation, run:

```powershell
runtime\python\python.exe -m src.training.verify_pytorch
```

Expected: PyTorch imports successfully and reports CPU availability. Confirm the shortcut target is the installed GUI executable, the installed `configs` directory contains no copied development path, and no external data-center file timestamps changed.

- [ ] **Step 5: Launch and close the installed UI**

Start the installed packaged GUI executable, verify the process remains running and the app requests a data center when unconfigured, then close only that disposable-install process.

- [ ] **Step 6: Record final artifact evidence**

Compute `Get-FileHash -Algorithm SHA256`, record byte and MB size, write `dist/installer/SHA256.txt`, and verify the recorded hash matches a fresh hash calculation.
