# 区间删失 RUL：数据合同与负例矩阵（设计包 B）

日期：2026-08-06　状态：**DESIGN ONLY / FAIL-CLOSED**　范围：Mendeley `zn82y35zr8` V4；不授权下载、实现、建表或训练。

## 1. Canonical manifest 与双向唯一映射

Manifest 顶层必填：`schema_version`、`source_id=mendeley_knee_v4_interval_rul`、`source_version=4`、`doi=10.17632/zn82y35zr8.4`、`license_id=CC-BY-4.0`、`license_url`、`license_snapshot_sha256`、`record_url`、`record_sha256`、`archive_official_name`、`archive_bytes`、`archive_sha256`、`final_url`、`content_length`、`etag`、`last_modified`、`downloaded_at_utc`、`parser_version`、`physical_cell_count`、`artifacts[]`、`mapping_audit`、`censoring_counts_by_stage`、`valid_for_interval_training=false`、`interval_training_authorized=false`。下载前未知的实体字段不得以空字符串假装已确认；缺任一必填实体字段即失效。

`artifacts[]` 每行必填：

```text
artifact_id, archive_member_path, member_sha256, member_bytes,
official_cell_token, physical_cell_id, stage_id, artifact_role,
protocol_reference_id, cycle_index_semantics, threshold_reference,
mapping_provenance
```

- `stage_id ∈ {soh100_to_80, soh80_to_60}`；`artifact_role ∈ {cycle, rpt, after_soh80}`。
- `artifact_id = sha256(archive_sha256 + "\0" + exact archive_member_path)`；主键为 `artifact_id`，规范化路径另设唯一约束。
- 正向函数 `F(artifact_id) -> (physical_cell_id, stage_id, artifact_role)` 必须单值；逆向索引 `G(physical_cell_id, stage_id, artifact_role) -> ordered set[artifact_id]` 必须无重复，且 `F(G(...))` 全部回到原三元组。允许一个角色存在多个文件，但每个文件只能属于一个 cell、一个阶段、一个角色。
- `physical_cell_id` 必须由随包官方 token 的确定性、无碰撞规则得到；两个 token 归一化为同一 ID，或同一 token 映射多个 ID，均失效。
- 同一 `physical_cell_id` 可出现在两个阶段；**同一 artifact、路径、内容实体不得跨 cell、跨阶段或跨角色复用**。内容 SHA 相同但确为两个官方独立实体时也不得自动合并，须保留两个 `artifact_id` 并由官方说明证明其角色。
- 可测试接口固定为 `inventory_archive(root, source_manifest) -> ArtifactInventory` 与 `validate_bidirectional_mapping(inventory, required_roles_by_stage) -> MappingAudit`。`MappingAudit` 必须输出逐 `(cell,stage)` 的 `cycle_artifact_ids/rpt_artifact_ids/after_soh80_artifact_ids`、集合 `C/R/A`、missing/duplicate/cross-cell/cross-stage 列表和 `valid`；adapter 不得只返回 Cycle/RPT 而漏掉 After-SOH80。
- `required_roles_by_stage` 及每角色期望文件数、After-SOH80 与第二阶段的权威归属，当前公开元数据不能确定；必须由下载后的官方 V4 随包说明/实体清单生成并记录其 provenance。该矩阵缺失，或任何要求集合不满足 `C_required=R_required=A_required=60`（如官方矩阵确实要求三类全覆盖），即 `INVALIDATED`；不得猜测“每 cell 各一个文件”。

Canonical 标签/审计行唯一键：

```text
(source_id, source_version, physical_cell_id, stage_id, prediction_cycle)
```

同一键只能有一个 censoring 状态。标签行另须包含 `condition_id`、`last_above_cycle`、`first_at_or_below_cycle`、`rul_lower_cycle`、`rul_upper_cycle`、`lower_inclusive`、`upper_inclusive`、`threshold_soh`、`threshold_reference`、`rpt_cadence_cycles`、`censoring_type`、`label_provenance_artifact_ids`。端点必须是物理 cycle 的整数（拒绝 bool/float/RPT 序号）；provenance 中每个 artifact 必须可由 `F` 回指同一 cell/stage。

## 2. Censoring 状态合同

| 状态 | 可执行构造（预测循环 `t`） | 训练 | 评估 |
|---|---|---|---|
| `interval_observed` | 有最后一次 `SOH>阈值` 的 `a` 与第一次 `SOH<=阈值` 的 `b`；`a<b, t<=a`；闭区间 `[a-t+1,b-t]` | 允许有限区间删失损失 | compatibility/enclosure、width、WIS、calibration |
| `right_censored` | 有协议可追溯的最后一次 above 观测 `c`，无合法 below；`t<=c`；`[c-t+1,+∞)`，故 `rul_upper_cycle=null` | 仅允许删失感知损失；不得填充上界 | 单独报告 lower-bound violation；不得混入有限区间均值 |
| `left_censored` | 首个有效阈值观测已 `<=阈值`，且无同阶段先前 above；有限下界不可识别 | 禁止；只写 audit | 禁止模型质量统计；只计 cell/row 数与原因 |
| `invalid_protocol` | 映射、阶段、阈值参考、cycle 语义、RPT 顺序、终止证据或 provenance 任一不满足合同 | 完全阻断 | 完全阻断；写 `INVALIDATED.json` 与 reason codes |

共同门禁：`rul_lower_cycle>=0`；有限上界必须为整数且 `lower<=upper`；`lower_inclusive=true`；observed 的 `upper_inclusive=true`，right 的上界及其 inclusive 均为 null。`prediction_cycle` 不得位于 `(a,b]` 或 EOL 后。文件末尾、最大 RPT 编号、文件名中的 cycle 范围均不能单独充当 `b`。阈值容量参考不明确时，全 cell/阶段为 `invalid_protocol`，不自行假设相对 BOL。

## 3. INVALIDATED 条件与 RED 负例矩阵

| 负例 | 必须结果 | 可执行断言/原因码 |
|---|---|---|
| manifest 缺 `member_sha256`、`threshold_reference` 或实体字段为空占位 | 全版本失效，两个授权保持 false | `MANIFEST_REQUIRED_FIELD_MISSING` |
| 60-cell 声称无法由实体清单得到唯一 `physical_cell_id` 集合 | 全版本失效；不能以出版方总数补名单 | `CELL_INVENTORY_UNPROVEN` |
| 同一 `(cell,stage,role,path)` 重复，或两个 token 归一化碰撞 | 全版本失效 | `DUPLICATE_ARTIFACT` / `CELL_ID_COLLISION` |
| 一个文件映射到 RW01 与 RW02，或同一路径同时标为两个阶段 | 全版本失效；禁止复制后“修复” | `CROSS_CELL_REUSE` / `CROSS_STAGE_REUSE` |
| 某 cell/stage 缺官方要求角色，或角色覆盖规则无法从随包材料确定 | 该版本失效；不得根据目录名补推 | `ROLE_COVERAGE_INCOMPLETE_OR_UNKNOWN` |
| RPT cycle 非整数/非严格递增、`a>=b`、端点跨 cell/阶段 | 对应 cell/stage 为 invalid；若身份或系统性协议问题则全版本失效 | `CYCLE_SEMANTICS_INVALID` / `BRACKET_INVALID` |
| 只有最后一次 above，代码把 file-end 当作 `b` 并生成有限区间 | **明确 RED**：必须拒绝；正确状态只能是有权威终止证据的 `right_censored`，否则 `invalid_protocol` | `FILE_END_IS_NOT_EOL` |
| left/invalid 行进入训练表，或 right 行被填入有限上界 | 构建失败且不发布半成品 | `CENSORING_ROUTE_VIOLATION` |

最小 RED fixture：`artifact_id=A` 同时出现 `(RW01,soh100_to_80,cycle)` 与 `(RW02,soh100_to_80,cycle)`，且 RW01 仅有 `last_above_cycle=100`、文件末尾 `150`、无 first-at-or-below RPT。期望准入返回 `INVALIDATED`，reason codes 同时包含 `CROSS_CELL_REUSE` 和 `FILE_END_IS_NOT_EOL`，`interval_labels.csv` 不得发布，两个授权字段均为 false。

> 未决下载后门禁：实际 60 个 cell token、各阶段必需角色/文件基数、After-SOH80 权威阶段归属、SOH80/SOH60 容量参考、物理 cycle 与 RPT 序号字段、官方终止/提前终止语义。任一项未由 V4 随包证据解决，就保持 fail-closed；本文不作外推。
