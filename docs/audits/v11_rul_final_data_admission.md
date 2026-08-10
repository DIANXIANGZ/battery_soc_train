# v11 RUL 最终数据准入结论

日期：2026-08-04  
状态：**终止语义取证路线关闭；`valid_for_training=false`；`training_authorized=false`。**

## 结论

1. MATR 当前只有 5 个 `official_continuation` 电芯可视为精确 observed RUL 标签来源；v11 中对应 9,381 个循环行。
2. 36 个 `official_cycle_life_eol` 候选不得升级：canonical detail JSON 虽已通过来源、绑定和实体指纹门禁，但 schema 没有终止原因或 EOL 末端流程字段。字段缺失不能推断 EOL，同类网络重试已经耗尽。
3. MATR 的 36 个候选与 5 个官方已知早停电芯继续保持 `right_censored`，共 41 个电芯、32,775 个循环行；这些行不得伪装为精确 RUL 监督。
4. 仅有 5 个精确 observed MATR 电芯不足以启动 RUL 烟雾或正式训练，也不足以宣称或验证 `MAE <= 1 cycle`。
5. Oxford 当前 8 个电芯、519 个诊断观测的中位采样步长为 100 个物理循环，EOL 只被夹在 100 或 200 循环宽的区间内；不得用于 `<=1-cycle` 点误差验收，也不得与 MATR 点标签混合平均。

## v11 MATR 可用规模

只读复核对象：

- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/04_公开电池规范数据/public_battery_corpus_v11/corpus_manifest.json`
- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/04_公开电池规范数据/public_battery_corpus_v11/public_battery_cycles.csv`

| 当前 provenance | 电芯数 | 循环行 | `rul_observed=1` 行 | 精确 RUL 点监督 | 当前允许用途 |
|---|---:|---:|---:|---|---|
| `official_continuation` | 5 | 9,381 | 9,381 | 标签语义允许，但规模与训练授权均不满足 | 只读统计、标签/协议审计；不得启动训练 |
| `official_cycle_life_eol` | 0 | 0 | 0 | 无 | 无；36 个候选禁止升级 |
| `observed_eol_crossing`（MATR） | 0 | 0 | 0 | 无 | 无 |
| `right_censored`（36 候选 + 5 早停） | 41 | 32,775 | 0 | 禁止 | 明确的删失分析、数据覆盖统计；不得作点标签 |

一致性检查：MATR 中 `rul_observed == 1` 与 `rul_cycles` 非空逐行完全一致；观察到的 5 个电芯为 `b1c0`–`b1c4`，每个电芯的 RUL 范围均从 1 循环延伸至其官方续接寿命。

## provenance 使用矩阵

| provenance / 协议 | 精确点回归 | 区间或删失任务 | `<=1-cycle` 验收 | 约束 |
|---|---|---|---|---|
| `observed_eol_crossing` | 仅当来源确实观测到精确物理 crossing，且循环索引、EOL 阈值和来源证据通过门禁 | 可 | 仅精确 crossing 协议可进入 | provenance 名称本身不充分，必须同时审查来源采样协议 |
| `official_continuation` | 可作为精确标签语义 | 可 | 数据规模、严格留出和训练授权满足后才可进入 | 当前 MATR 只有 5 个电芯，因此禁止训练/验收 |
| `official_cycle_life_eol` | 当前无已准入对象 | 不适用 | 禁止 | 36 个候选已被最终裁定为不可升级 |
| `right_censored` | 禁止 | 可用于显式删失/生存分析 | 禁止 | 文件终点、Table 9 数值或字段缺失均不能成为 EOL |
| Oxford 当前 `observed_eol_crossing` 命名数据 | 禁止作为 1-cycle 精确点标签 | 仅独立的 100-cycle 网格或区间删失诊断 | 禁止 | 8 电芯、519 观测；100-cycle 中位网格；EOL 区间宽 100–200 cycles |

## Oxford 协议边界

Oxford 当前 canonical source 的标签全部是 100 的倍数；470 个相邻观测步长为 100 cycles，40 个为 200 cycles，另 1 个为 300 cycles，且没有 1-cycle 间隔观测。真实 80% crossing 未被逐循环观察，只能位于最后一次阈值上方观测与首次阈值下方观测之间。

因此允许用途仅为：

- 单独报告的 interval-censored RUL 分析；
- 单独报告的 100-cycle-grid 诊断；
- 作为获取更高分辨率、权威 EOL 来源前的可观测性证据。

禁止用途包括：

- `<=1-cycle` 点误差验收；
- 与 MATR 预测或误差混合平均；
- 将网格命中解释为逐循环准确；
- 通过放宽阈值包装为达标。

## 数据质量裁定

| 发现 | 严重度 | 证据 | 影响 |
|---|---|---|---|
| MATR 精确 observed 电芯仅 5 个 | Critical | v11 manifest：5 cells / 9,381 observed cycle rows | 无法形成可信的严格未见电芯训练、验证和测试规模 |
| 36 个候选缺少可验证终止语义 | Critical | `v11_matr_b1c31_detail_curl_final_audit.json`：完整 fingerprint，但无 termination/EOL 字段 | 不得升级 provenance，不得生成精确 RUL 标签 |
| 5 个早停与 36 候选共 41 电芯均删失 | Critical | v11 manifest：41 cells / 32,775 right-censored rows | 只能进入明确删失任务，不能作点回归监督 |
| Oxford 目标分辨率为 100–200 cycles | Critical（针对 1-cycle 验收） | `v10_oxford_rul_observability.json` | 目标本身不可识别到 1 cycle，与模型容量无关 |
| v11 训练授权关闭 | Critical | `valid_for_training=false`, `training_authorized=false` | 任意 smoke/formal 训练均被治理边界禁止 |

## 最终运行边界

- 禁止 MATR RUL 烟雾训练与正式训练。
- 禁止以 5 电芯规模启动训练或声称满足 `<=1-cycle`。
- 禁止将 36 个候选提升为 `official_cycle_life_eol`。
- 禁止把 41 个删失电芯的文件终点、Table 9 cycle life 或空缺字段当作 EOL。
- 禁止 Oxford 进入 1-cycle 主验收。
- 只有新的、独立、权威且高分辨率的 EOL 数据通过来源、单位、标签因果、删失和严格留出门禁，并获得总工程师明确批准后，才可重新评估训练准入。

## 证据索引

- `docs/audits/v11_matr_b1c31_detail_curl_final_audit.json`
- `docs/audits/v11_matr_41_cell_unique_mapping_audit.json`
- `docs/audits/v11_matr_41_cell_unique_mapping.csv`
- `docs/audits/v11_matr_cycle_life_per_cell.csv`
- `docs/audits/v11_matr_batch2_source_verification.json`
- `docs/audits/v10_oxford_rul_observability.json`
- `docs/audits/v10_oxford_rul_observability.csv`
- `docs/audits/v10_phase12_pretraining/rul_source_protocols.json`

本文件是最终数据准入裁定，不是训练授权。
