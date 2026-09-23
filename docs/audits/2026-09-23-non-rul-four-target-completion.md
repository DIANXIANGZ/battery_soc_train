# 非 RUL 四目标正式基线完成归档

状态：`COMPLETE_FOUR_TARGET_SCOPED_BASELINES`

本文件是只读汇总，不重跑训练、不修改数据版本、不覆盖历史报告、不执行 Git。四个目标均有正式 PyTorch 结果，但每个结果都只在其明确范围内成立，不能合并解释为跨电芯、跨来源或跨目标泛化。

对应机器可读归档：
`docs/audits/2026-09-23-non-rul-four-target-completion.json`

JSON SHA-256：`219bd978c482e512e833ac134e82c0391803407dc60b22d25b6a53b2d6ac1ccd`

## 四目标结论

| 目标 | 正式状态 | 适用范围 | 主要指标 |
|---|---|---|---|
| SOC | `PYTORCH_FORMAL_PASS_SCOPED` | `LGHG2_001` 单电芯、六个完整工况留出 | 测试 411,135 行；宏 MAE `3.05958233824622e-06`；宏 RMSE `3.850856181081782e-06` |
| 系统级 SOE | `PYTORCH_FORMAL_PASS_SCOPED` | Zenodo 8381142 社区储能系统；不是电芯级 SOE | 训练/测试 21,205/4,933 行；MAE `13.538709044079217`；RMSE `16.552627288336616` |
| SOH | `PYTORCH_FORMAL_PASS_SCOPED` | `UNIBO_CALIBRATION_CELL_001` 单校准电芯趋势 | 训练/测试 17/4 行；测试 MAE `0.003233805298805237`；RMSE `0.0032712346874177456` |
| SOT | `PYTORCH_FORMAL_PASS_SCOPED` | `source-native-temperature` 逐条基线；仅已见电芯/工况 | 训练/测试 9,693,376/1,558,205 行；MAE `5.016611990628302`；RMSE `10.040537547113313` |

## 关键边界

- SOT 标签只称 `source-native-temperature`，不宣称摄氏度；特征是当前行电压/电流，不使用温度或未来轨迹。
- SOC 只证明单电芯跨工况留出；SOH 只证明单校准电芯趋势；系统级 SOE 只证明社区储能系统级任务。三者都不支持未知电芯泛化。
- `energy_proxy` 仍是累计放电能量补充结果（`discharge_energy_wh_cumulative`，Wh），`native_soe=false`，不能替代系统级 SOE。
- RUL、v9、v10、v11 及冻结资产未读取、未混入；冻结 denylist SHA-256 为 `44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`。
- 历史 `2026-09-23-non-rul-pytorch-final-readiness.*` 曾记录 SOT 为 `BLOCKED_INVALIDATED`。本归档只追加后续 SOT READY、smoke 和 formal 证据，不改写历史文件。

## 证据绑定

完整的每目标数据版本、代码/配置、正式结果工件路径与 SHA-256 均在同名 JSON 中逐项列出。已对四个正式结果目录做只读回读：每个目录严格包含五个结果工件，结果哈希与对应归档一致；SOT 结果 1,558,205 行且仅测试组 `cell_40ah_1|40Ah|2C|100%DOD`，数值有限、禁用语义命中为 0。

四目标代码/配置与结果归档均保持独立命名空间；本轮未改变数据版本或历史结果。新归档完成后交新测试工程师做文档/路径/哈希独立复核；复核 PASS 后再交 Git 管理员按精确清单处理，不在本工作区直接提交。
