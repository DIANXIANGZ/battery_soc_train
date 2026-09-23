# 非 RUL PyTorch 九项任务最终状态

## 结论

九项计划现已完成可交付范围内的最终封板：SOC、系统级 SOE 和 SOH 均有经过独立验收的 PyTorch 正式训练结果；SOT 保持明确阻断，不以其他目标的成功掩盖。总体状态为 `COMPLETE_WITH_SCOPE_LIMITS`。

本次封板只回读现有证据，没有重新训练、修改数据版本、读取 RUL 或冻结资产，也没有执行 Git。

## 九项任务状态

| 任务 | 状态 | 结果 |
|---|---|---|
| 1 公共数据合同 | PASS | 统一样本字段、分组和拒绝规则已落地 |
| 2 数据版本与回滚 | PASS | 固定四文件、指纹回读、原子发布和失败清理可用 |
| 3 SOT | BLOCKED | 点式温度版本只有 `INVALIDATED.json`，没有可训练行 |
| 4 SOC | PASS | 单电芯六工况留出的 PyTorch 正式训练通过 |
| 5 SOE | PASS（限系统级） | 社区储能系统 SOE PyTorch 正式训练通过 |
| 6 SOH | PASS（限单电芯） | 单校准电芯趋势 PyTorch 正式训练通过 |
| 7 PyTorch 入口 | PASS | 入口、指纹、目标和冻结资产拒绝测试通过 |
| 8 目标试运行与训练 | 部分完成 | SOC、系统级 SOE、SOH 通过；SOT 因数据阻断未运行 |
| 9 最终封板 | COMPLETE_WITH_SCOPE_LIMITS | 三目标正式通过，一目标明确阻断 |

## 已完成目标

### SOC

- 范围：仅 `LGHG2_001` 已见单电芯的六个完整工况留出，不代表未知电芯或跨来源泛化。
- 模型：`torch.nn.Linear(4,1)` 闭式 Ridge。
- 测试预测：411,135 行。
- 宏平均 MAE：`3.05958233824622e-06`。
- 宏平均 RMSE：`3.850856181081782e-06`。
- 结果目录：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/07_SOC轻量基线/soc-lightweight-condition-v1-2026-08-27/pytorch-linear-formal-v1`
- 归档：[2026-09-22-soc-pytorch-linear-formal-summary.md](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-09-22-soc-pytorch-linear-formal-summary.md)

### 系统级 SOE

- 范围：Zenodo 8381142 社区储能系统，不代表单电芯或未知电芯泛化。
- 标签：`soe_source_value`；来源未明确单位，因此误差不解释为百分比或 kWh。
- 模型：CPU `torch.nn.Linear(3,1)` 最小二乘。
- 训练：21,205 行、238 个 `RequID` 组。
- 测试：4,933 行、60 个 `RequID` 组，与训练组零重叠。
- MAE：`13.538709044079217`。
- RMSE：`16.552627288336616`。
- 结果目录：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/08_系统SOE轻量基线/system_soe-baseline-v1/pytorch-linear-formal-v1`
- 归档：[2026-09-23-system-soe-pytorch-formal-training.md](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-09-23-system-soe-pytorch-formal-training.md)

### SOH

- 范围：`UNIBO_CALIBRATION_CELL_001` 单校准电芯趋势，不代表跨电芯泛化。
- 模型：`torch.nn.Linear(1,1)`，SGD。
- 训练 17 行，测试 4 行。
- 测试 MAE：`0.003233805298805237`。
- 测试 RMSE：`0.0032712346874177456`。
- 结果目录：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/09_SOH单电芯小样本基线/soh-single-cell-calibration-v1-2026-09-04/pytorch-linear-v1-formal-2026-09-20-v3`

## 仍阻断目标

SOT 的点式数据版本目录只含 `INVALIDATED.json`，SHA-256 为 `044f70f2459361409fe42582ce09364a7369c3497db2c155e0d0044005365eef`。没有 `READY.json`、没有训练样本，也没有启动烟雾或正式训练。若未来要求四目标全部可训练，唯一剩余工作是单独解决 SOT 数据来源或目标定义；不得重开该失效版本。

## 补充结果与安全边界

- `energy_proxy` 的累计放电能量结果继续保留，但它不是系统级 SOE，也不替代 SOE 结果。
- RUL、v9、v10、v11 和其他冻结资产继续冻结，本次封板没有读取或混入。
- 本轮没有执行 Git；是否交付 Git 管理员属于后续发布步骤。

## 下一步

当前限定范围内没有待补训练。最短的下一阶段是将已通过独立测试的代码、配置和归档整理成交付清单，交给 Git 仓库管理员；如果项目必须实现四目标齐全，则另开 SOT 数据修复阶段。
