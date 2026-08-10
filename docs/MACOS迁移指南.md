# 迁移到 macOS

本项目的代码和数据中心是分开的。不要复制 Windows 的 `.venv`、`.idea`、`.run`，也不要在 macOS 上运行 `.bat`、`.ps1` 或 Windows 安装程序。

## 在 Windows 导出

在项目根目录用 PowerShell 运行：

```powershell
scripts\export_macos_bundle.ps1
```

它会在项目的上一级创建 `battery_soc_project_macos_transfer`，其中包括：

- `battery_soc_project_macos_source.zip`：Mac 所需代码、测试、文档和脚本；不含 Windows 虚拟环境。
- `SHA256.txt`：代码包校验值。
- `data_inventory.csv`：当前可访问的数据文件清单（路径、大小、修改时间）。

该导出不会复制或改动数据中心。将整个 `E:\SOC电池数据中心` 作为一个目录单独复制到移动硬盘或 NAS；数据量约 7.07 GiB（本次盘点时 943 个文件）。保持目录层级和文件名不变。

## 在 Mac 导入

1. 解压 `battery_soc_project_macos_source.zip` 到，例如 `~/Projects/battery_soc_project`。
2. 将数据中心复制到本机磁盘或已挂载外接盘，例如 `/Volumes/SOCData/SOC电池数据中心`。
3. 安装 Python 3.12。安装后确认 `python3.12 --version` 可用。
4. 在项目根目录运行（替换为你的实际数据路径）：

```bash
bash scripts/macos_setup.sh --data-root "/Volumes/SOCData/SOC电池数据中心"
bash scripts/macos_verify.sh
```

`macos_setup.sh` 会新建 `.venv-macos`、安装 `requirements.txt` 中锁定的依赖，并只在 Mac 副本中更新 `configs/paths.json`。它不会使用或修改 Windows 电脑上的配置。

## 校验标准

- 在 Mac 上执行 `shasum -a 256 battery_soc_project_macos_source.zip`，结果应与 `SHA256.txt` 一致。
- `bash scripts/macos_verify.sh` 最后应输出 `MACOS_TRANSFER_VERIFIED`。
- 该验证只导入依赖、读取数据中心配置并运行测试；不会训练模型、删除数据或覆盖基线结果。

## 兼容性说明

训练代码和 Tkinter 桌面界面可在 macOS 的 Python 环境运行；Windows 专用的 `.bat` 启动器、PowerShell/Inno Setup 安装器不在 Mac 上使用。若运行桌面界面时提示缺少 `tkinter`，请按你安装 Python 的发行版说明补装其 Tk 组件，再重新运行验证。
