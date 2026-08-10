# NASA 五状态电池预测：数据与训练说明

## 这次新增了什么

本项目保留原有的 `A123 SOC` 任务，同时新增独立的 `NASA 五状态` 任务。新任务一次预测五个量：SOC、SOH、SOE、RUL 和 SOT，不会覆盖 A123 的数据、模型或图表。

## 数据从哪里来

原始数据位于：

`E:\SOC电池数据中心\01_原始数据\03_NASA_PCoE_多状态原始数据\randomized`

训练数据位于：

`E:\SOC电池数据中心\02_训练数据\02_NASA_五状态训练数据\nasa_randomized_multistate_samples.csv`

数据来自 NASA PCoE Randomized Battery Usage Data Set。每个压缩包目录有 `download_manifest.json`，记录下载来源、下载时间与校验值；训练数据目录中的 `data_audit.json` 和 `split_manifest.json` 记录样本数量、标签构造方式与电芯划分。

## 五个预测量的含义

| 名称 | 文件中的列 | 含义与单位 |
|---|---|---|
| SOC | `soc` | 单个参考放电过程中的剩余荷电比例，范围约为 0 到 1。 |
| SOH | `soh` | 当前参考放电容量 / 首次参考放电容量，无单位比例。 |
| SOE | `soe` | 当前时刻至该参考放电结束的剩余能量 / 初始参考放电能量，无单位比例。 |
| RUL | `rul_cycles` | 距离容量首次降至初始容量 70% 还剩多少个参考放电循环，单位为循环。 |
| SOT | `sot_c` | 数据集中实测电芯温度，单位为摄氏度。它是温度状态代理量，不代表电芯内部三维温度场。 |

## 防止数据泄漏的方法

训练、验证、测试按电芯严格分开：RW9 与 RW10 用于训练，RW11 用于验证，RW12 仅用于最终测试。LSTM 连续窗口不会跨越电芯边界，也不会跨越一次参考放电循环边界。标准化均值和标准差只由训练电芯计算。

## 改进模型如何工作

训练平台现在使用混合五状态架构：SOC 与 SOE 由采样点级 LSTM 预测；SOT 定义为未来 5 分钟温度，由独立的温度残差 LSTM 相对当前温度预测；SOH 使用循环级退化特征；RUL 根据因果 SOH 轨迹投影至 70% 阈值。四个 RW 电芯依次作为完全未见测试电芯，最终指标是四折宏平均。

旧五头共享 LSTM 及其历史结果保持冻结，只作为旧版基线，不再作为训练平台默认入口。

## 如何重新训练

在 `outputs\battery_soc_project` 目录中运行：

```powershell
..\..\work\soc_venv\Scripts\python.exe -m src.training.train_nasa_hybrid `
  --state-data "E:\SOC电池数据中心\02_训练数据\03_NASA_生命周期训练数据\nasa_state_future_samples.csv" `
  --lifecycle-data "E:\SOC电池数据中心\02_训练数据\03_NASA_生命周期训练数据\nasa_lifecycle_cycles.csv" `
  --results-dir "E:\SOC电池数据中心\03_模型与实验结果\04_NASA_五状态模型与结果\新实验名称" `
  --stage formal --seed 42
```

每一轮会输出 `PROGRESS: 百分比`，桌面训练平台可据此显示进度。请为每次训练使用新的结果目录，避免覆盖历史实验。

## 如何阅读结果

一个完整实验目录包含：

- `aggregate_metrics.json`：五个目标的四折宏平均、最差电芯和基线结论；
- `test_RW*/state`：SOC、SOE 模型与预测；
- `test_RW*/temperature`：未来温度模型、预测和持续性基线；
- `test_RW*/lifecycle`：SOH、RUL 预测及退化轨迹审计；
- `run_config.json`：训练参数和两个输入 CSV 的 SHA-256；
- `*_prediction.png`：五张四电芯分面预测图。

MAE 是平均绝对误差，越小越好；RMSE 对较大的单次误差更敏感，也越小越好。SOC、SOH、SOE 的数值为比例，例如 MAE `0.037` 约等于 3.7 个百分点；RUL 以循环数解释；SOT 以摄氏度解释。

## 当前正式实验

正式结果目录：

`E:\SOC电池数据中心\03_模型与实验结果\04_NASA_五状态模型与结果\run_20260726_5state`

该目录是冻结的旧版单电芯基线。改进模型使用每次平台运行产生的独立四折结果目录；由于仍只有四个电芯，不能直接视为所有型号电池或真实车辆工况上的通用结论。
