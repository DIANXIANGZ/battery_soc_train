# 2026-08-03 MATR v8 断点记录

## 当前状态

- `public_battery_corpus_v7` 已作废：MATR 原始时间 `t` 为分钟，v7 曾按秒处理，导致 SOC/SOE 积分缩小 60 倍。
- `strict_smoke_v7_seed_43` 已作废：所有指标均不得使用，包括当时的 SOC/SOT “达标”结果。
- v8 已完成以下修正：
  - MATR 分钟转秒；
  - 排除并记录 2 个容量异常循环：`b1c0/cycle 12` 和 `b1c18/cycle 40`；
  - 读取 MATR 官方 `cycle_life` 作为 RUL 监督目标，不将它作为输入特征；
  - Stanford 首循环历史容量/能量特征的标称值已改为 1.1 Ah / 3.63 Wh。
- 相关回归测试在 v8 构建前为 `42 passed, 5 subtests passed`。
- `public_battery_corpus_v8` 也已作废：用 stride-50 降采样电流做矩形积分仍会扭曲累计电量；MATR 末端积分电量/原始 Qd 比值范围为 0.846–26.633，未通过准入。
- v8 未启动任何正式训练，也没有可用的下游评估结果。

## 尚未完成

- 尚未实现：使用 MATR 原始、逐时刻可观测的 `Qd` 构造因果累计放电量，并用 `dQ * V` 构造累计能量。
- 尚未重建 `public_battery_corpus_v9`。
- 尚未重跑 v9 的容量/能量参考一致性、Qd 末端一致性、因果泄露回归、异常循环排除和旧版本拒绝测试。
- 上述全部通过前，不得启动严格烟雾或正式训练。

## 明天恢复入口

1. 先为 MATR 原生 Qd 因果累计标签增加失败测试，要求降采样前计算、改变未来尾段不影响前缀标签。
2. 修改 Stanford 适配器与状态标签派生，优先使用原生累计 Qd；SOE 由当前及过去的 Qd 增量与电压计算。
3. 跑聚焦回归测试，通过后构建新目录 `public_battery_corpus_v9`，不覆盖 v7/v8。
4. 对 v9 运行并留档所有硬门禁；只有整体通过后才能开始新的严格烟雾训练。

## 权威标记

- v7 数据作废标记：`public_battery_corpus_v7/INVALIDATED.json`
- v7 烟雾结果作废标记：`strict_smoke_v7_seed_43/INVALIDATED.json`
- v8 数据作废标记：`public_battery_corpus_v8/INVALIDATED.json`
- v7/v8 质量报告目录中均有对应 `INVALIDATED.json`。
