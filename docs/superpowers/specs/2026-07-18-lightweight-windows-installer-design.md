# Lightweight Windows Installer Design

## Goal

Produce a Windows setup executable named `SOC电池训练平台安装程序.exe`. A user on another 64-bit Windows computer can install, launch, and uninstall the desktop platform without configuring Python manually and without changing an existing Python or PyTorch installation.

## Packaging approach

Use an Inno Setup bootstrap installer. PyInstaller produces a lightweight standalone Tkinter GUI executable without PyTorch, while the setup executable also contains the platform training source, environment scripts, and an official registration-free CPython NuGet runtime. Large training packages are downloaded during installation, so the distributable remains small enough to copy through ordinary file sharing.

The installer targets 64-bit Windows 10 and Windows 11. The install wizard allows a custom destination. The default is a per-user application directory; users with limited system-drive space can select another drive.

## Isolated runtime

The application owns a private Python runtime under its installation directory. Setup extracts the official CPython NuGet package directly into that directory, avoiding Python registration, PATH changes, and conflicts with another installation of the same Python version. Package installation always invokes that runtime explicitly and never calls a global `python`, `pip`, or `py` command.

The runtime installs the pinned application dependencies, including CPU PyTorch, NumPy, Pillow, and OpenPyXL. It does not add Python to `PATH`, register file associations, install a global Python launcher, or alter an existing virtual environment.

The installed runtime may occupy approximately 1–2 GB even though the bootstrap setup executable is much smaller.

## Data separation

Training data, models, experiment results, and run logs remain outside the program directory in the user-selected data center. The installer does not package the current A123 dataset or existing experiment outputs.

On first launch, the platform asks the user to select a compatible data center when no valid saved path is available. Uninstallation removes application and private-runtime files but does not delete the external data center.

## Installation flow

1. The setup wizard displays the network and disk-space requirements.
2. The user selects an installation directory and optional desktop shortcut.
3. The installer copies the platform and private-runtime bootstrap files.
4. A hidden installation helper extracts the registration-free runtime and downloads pinned packages over HTTPS.
5. The helper runs the existing PyTorch verification module with the private interpreter.
6. Only after verification succeeds does setup create the final shortcuts and report success.

The desktop and Start Menu shortcuts launch the packaged Tkinter GUI executable without a command-prompt window. The working directory is always the installed application directory; training subprocesses use the private runtime.

## Failure handling and logs

The environment helper writes an installation log under the installed application's `logs` directory. Network, package, disk-space, or verification failures cause setup to report failure rather than claiming a usable installation.

A failed installation preserves the log for diagnosis. Re-running setup is idempotent: valid downloaded packages may be reused, and the private runtime can be repaired without touching external training data.

## Uninstallation

The standard Windows uninstall entry removes shortcuts, platform code, installer-owned logs, and the private runtime. It must not remove the configured external data center, training data, models, or experiment results.

## Build outputs

The project gains reproducible installer sources and a build script. Generated build intermediates remain outside the source tree or in an ignored build directory. The user-facing artifact is:

`dist/installer/SOC电池训练平台安装程序.exe`

The final handoff includes a SHA-256 hash and measured file size.

## Acceptance checks

- The setup executable builds successfully on the current Windows machine.
- A clean test installation uses only its private Python runtime.
- The installed shortcut opens the current Tkinter platform without a console window.
- `src.training.verify_pytorch` succeeds through the installed private interpreter.
- Platform unit tests pass before packaging.
- The application can locate or request an external data center.
- Uninstallation is registered and never targets external data-center files.
- The final setup executable exists at the documented path, with verified size and SHA-256.
