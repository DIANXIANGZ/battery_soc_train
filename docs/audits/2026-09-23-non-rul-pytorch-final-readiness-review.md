# 非 RUL PyTorch 最终封板独立复核回执

复核日期：2026-09-23（Asia/Shanghai）

## 复核范围

仅只读复核以下两份最终归档及其引用的正式结果路径、工件指纹、SOT `INVALIDATED` 实体和范围/安全声明：

- `2026-09-23-non-rul-pytorch-final-readiness.json`：4981 bytes，SHA-256 `7f974ec83266404228ad10d14d6f4eb62e739e3279f23f5d2eb7529a708bccb3`
- `2026-09-23-non-rul-pytorch-final-readiness.md`：4314 bytes，SHA-256 `facc4bd1e6d0f19422b0cbc6cac0cb790ffc7b0e34ecd6bfa66b1b0f7e558162`

未运行训练或测试，未修改代码、配置或数据版本，未执行 Git。

## 复核结论

**PASS（文档与既有事实一致，`COMPLETE_WITH_SCOPE_LIMITS`）**。

- 九项任务状态与 JSON/Markdown 的对应表述一致：公共合同、不可变版本、PyTorch 入口和三项目标正式结果通过；SOT 保持 `BLOCKED_INVALIDATED`；目标试运行任务为部分完成；最终范围受限。
- SOC、system-level SOE、SOH 三个正式结果目录均存在，且各自严格包含五项工件；工件 SHA-256 与归档及对应正式报告一致。
- SOC 范围为已见单电芯 `LGHG2_001` 的六工况留出，411,135 条测试预测，宏平均 MAE/RMSE 为 `3.05958233824622e-06` / `3.850856181081782e-06`。
- system-level SOE 范围为 Zenodo 8381142 社区储能系统，训练/测试为 21,205/4,933 行、238/60 个 RequID 组，MAE/RMSE 为 `13.538709044079217` / `16.552627288336616`；不代表电芯级或未知电芯泛化，单位保持 `unspecified_source_unit`。
- SOH 范围为 `UNIBO_CALIBRATION_CELL_001` 单校准电芯趋势拟合，训练/测试为 17/4 行，测试 MAE/RMSE 为 `0.003233805298805237` / `0.0032712346874177456`；不代表跨电芯泛化。
- SOT 版本仅保留 `INVALIDATED.json`，SHA-256 为 `044f70f2459361409fe42582ce09364a7369c3497db2c155e0d0044005365eef`，未创建 READY。
- `energy_proxy` 明确是 `discharge_energy_wh_cumulative` 累计放电能量补充结果，`native_soe=false`，不替代 system-level SOE。
- RUL、v9、v10、v11 及其他冻结资产继续冻结，归档声明未读取或混入；本轮归档未重新训练、未修改数据版本、未执行 Git。

本回执完成最终归档的独立文档复核，不改变原归档文件，也不新增任何训练或发布授权。
