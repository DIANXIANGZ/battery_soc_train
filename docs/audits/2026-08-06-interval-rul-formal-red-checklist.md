# 区间删失 RUL：正式送测 RED 清单

日期：2026-08-06  
状态：**DESIGN-ONLY 送测材料；不授权下载、实现、数据版本或训练。**

## 送测范围与依据

本清单只把现有正式设计中的失败断言整理为测试可核对的四类 RED 项；不引入新方案或替代口径。测试时须以以下三份正式文档为唯一合同，并将锁定设计包 A/B 仅作为公式和数据合同的溯源依据：

- `docs/superpowers/specs/2026-08-06-mendeley-knee-interval-rul-design.md`
- `docs/superpowers/plans/2026-08-06-mendeley-knee-interval-rul.md`
- `docs/audits/2026-08-06-interval-rul-executable-one-page.md`

本阶段仅审阅文档可测试性；不得因此启动下载、代码、数据版本或训练。

## RED-1：文件映射与 After-SOH80

| ID | 最小夹具/输入 | 预期 fail-closed 结果 |
|---|---|---|
| M1 | `MappingAudit` 仅输出 Cycle/RPT，不含任一 `(cell,stage)` 的 `after_soh80_artifact_ids` 或集合 A | `INVALIDATED`；不得发布标签；`valid=false` |
| M2 | `required_roles_by_stage`、文件基数或 After-SOH80 的权威阶段归属缺失，或无官方 provenance | `INVALIDATED`，原因 `ROLE_COVERAGE_INCOMPLETE_OR_UNKNOWN` |
| M3 | 同一 artifact/path/content 映射给两个 cell、两个阶段或两个角色；或 `F(G(...))` 不回到原三元组 | 全版本 `INVALIDATED`，原因含 `CROSS_CELL_REUSE`、`CROSS_STAGE_REUSE` 或映射不互逆 |
| M4 | 60-cell 名单不能由实体清单唯一证明，或官方 token 规范化碰撞 | 全版本 `INVALIDATED`，原因 `CELL_INVENTORY_UNPROVEN` 或 `CELL_ID_COLLISION` |

## RED-2：有限区间指标、嵌套校准与分母

| ID | 最小夹具/输入 | 预期 fail-closed 结果 |
|---|---|---|
| E1 | `Y=[4,6]`、`P90=[7,9]` | 计算 `C=0,E=0,W=2,D=1,WIS=4`；不得以 compatibility 或 enclosure 代替 WIS |
| E2 | 同一行 `P50=[3,8], P80=[4,7], P90=[5,9]` | 非嵌套；整个 `(stage,fold)` 为 `NOT_COMPARABLE` 且 FAIL |
| E3 | `Y=[8,+∞)`、`P90=[2,7]` | lower-bound violation=1；该行不得进入有限 compatibility/enclosure/width/WIS/calibration 分母 |
| E4 | 预测缺失、非有限、端点倒置，或 finite fold 无有限观测行 | `NOT_COMPARABLE` 且 FAIL；不得删行或以 0/NaN 替代 |

校准固定使用 enclosure：同一批有限行须提供嵌套的 50/80/90 区间，`ICE=mean_alpha(abs(EC_alpha-alpha))`；任何无法构成该计算的输出均归 E2/E4 失败。

## RED-3：阶段独立 LOCO 与非训练基线

| ID | 最小夹具/输入 | 预期 fail-closed 结果 |
|---|---|---|
| L1 | 任一 LOCO fold 的基线读取测试 cell、测试标签、测试特征或模型输出 | FAIL；基线只能用该 `(stage,fold)` 训练 cells 的 `interval_observed` 行 |
| L2 | 训练折没有有限观测行（`m=0`） | `NOT_COMPARABLE` 且 FAIL；不得用测试折、全体数据或无穷上界补造基线 |
| L3 | 模型与 nearest-rank 基线的 mean width 或 WIS 任一相等 | tie，FAIL；“优于”必须两项均严格小于 |
| L4 | 两阶段共享 fold、归一化器、特征选择、早停或宏平均，或按样本行数微平均掩盖失败 fold | FAIL；必须阶段独立、按 cell/fold 等权宏平均 |

固定基线为 `B_alpha=[Q_q(L),Q_(1-q)(U)]`，`q=(1-alpha)/2`，`Q_p=x_(max(1,ceil(mp)))`。NaN、口径不一致或无测试有限行与 L2 同样 fail-closed。

## RED-4：删失构造与路由

| ID | 最小夹具/输入 | 预期 fail-closed 结果 |
|---|---|---|
| C1 | `a=100,b=150,t=101` 试图构造 observed 标签 | 拒绝；prediction cycle 不得位于 `(a,b]` 或 EOL 后 |
| C2 | 只有 `last_above_cycle=100`，文件结束为 150，却将 150 当 `first_at_or_below_cycle` | 拒绝有限标签，原因含 `FILE_END_IS_NOT_EOL`；仅在有协议证据时可为 right-censored，否则 `invalid_protocol` |
| C3 | right-censored 行被填入有限上界、转为中点/点标签，或进入有限 interval loss / WIS / calibration | 构建失败，原因 `CENSORING_ROUTE_VIOLATION`；不得发布半成品 |
| C4 | left-censored 或 invalid_protocol 行进入训练标签或模型质量统计 | 构建失败；left 仅审计，invalid 写 `INVALIDATED.json` |

right-censored 的唯一允许评估输出是其下界违例 `1[u90<L]`；它不参与有限指标或基线优于判定。若未来需要 censored likelihood，必须另行设计并验收。

## 测试结论规则

测试工程师需确认四类 RED 均有明确、无冲突的合同断言，并同三份正式文档的 SHA-256 一起存档。任何 RED 项无法映射到上述正式合同、任何口径冲突或任何未通过项，均为 **FAIL**，并保持下载、实现、数据版本和训练冻结。
