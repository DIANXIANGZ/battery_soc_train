# 区间删失 RUL 一页执行方案

日期：2026-08-06  
当前状态：**DESIGN ONLY；下载、数据版本、训练均未授权。**

## 独立任务合同

- 唯一来源候选：Mendeley `zn82y35zr8` V4，DOI `10.17632/zn82y35zr8.4`，CC BY 4.0。
- `soh100_to_80` 与 `soh80_to_60` 是两个独立任务，分别建表、LOCO、校准和报告；不得与彼此或 MATR/Oxford/NASA 混合。
- 若 last-above RPT 为 `a`、first-at-or-below RPT 为 `b`，则 EOL 整数闭区间为 `[a+1,b]`。在预测循环 `t<=a`，RUL 标签为 `[a-t+1,b-t]`。
- `interval_observed` 使用有限区间；`right_censored` 使用 `[lower,+∞)`，v1 只审计下界违例、不进入有限区间训练/校准；`left_censored/invalid_protocol` 只审计。file-end 永远不是 EOL 证据。
- 严格点 RUL 和 v11 继续冻结；新区间任务禁止点 MAE、`<=1-cycle`、精确 RUL 或等价声明。

## 下载请求（等待批准）

| 字段 | 请求 |
|---|---|
| 官方入口 | `https://data.mendeley.com/datasets/zn82y35zr8/4` |
| 唯一文件 | `Battery raw data.zip`，页面显示约 1.38 GB |
| 用途 | 核验 60 cell 的 Cycle/RPT/After-SOH80 映射、实际 bracket、终止和删失 |
| 空间 | 预留至少 4.5 GB；原包只读，解析和审计独立目录 |
| 校验 | 固定 V4/DOI/CC BY；记录 URL 链、2xx、Content-Length、ETag、Last-Modified、UTC，计算本地 SHA-256 |
| 停止条件 | 登录/OAuth、401/403/429、TLS/非2xx、访问限制、不明重定向、许可或版本不一致；不重试、不用镜像 |

不得猜测 file API URL。获批后只能从 V4 页面可见文件项解析官方实际 URL；若无法在无认证公开链路中取得，来源停止。

## 实施与验收顺序

1. **来源准入**：许可证、版本、文件实体与 60-cell inventory 全部可复核；否则停止。
2. **合同 TDD**：先 RED 后 GREEN，实现整数闭区间、四种 censoring 和两个固定 stage；拒绝浮点/布尔 cycle、负区间和未知阈值参考。
3. **adapter TDD**：`ArtifactInventory` 必须覆盖 Cycle/RPT/After-SOH80；`F(artifact)->(cell,stage,role)` 与 `G(cell,stage,role)->artifacts` 双向唯一。每阶段必需角色/文件基数和 After-SOH80 归属只能由随包官方说明生成；未知、缺失、重复、跨 cell/阶段/角色复用或 chunk 重叠使整版本失效。
4. **独立 corpus**：写新目录 `mendeley_knee_interval_rul_v1`，不使用 v12、不覆盖 v11；失败原子写 `INVALIDATED.json`。
5. **指标/LOCO TDD**：预测为嵌套的 50/80/90% 区间。对标签 `[L,U]` 与预测 `[l,u]`，`C=1[相交]`、`E=1[预测包含标签]`、`W=u-l`、`D=max(L-u,l-U,0)`、`WIS=W+2D`；校准只用 enclosure，`ICE=mean|ECα-α|`。逐 cell/fold 等权宏平均；右删失只报告 `1[u90<L]`，不进有限分母。

每个 LOCO fold/stage 的基线只用训练有限行，nearest-rank `Q_p=x_(max(1,ceil(mp)))`，输出常量 `Bα=[Q_q(L),Q_(1-q)(U)]`。未来门禁在每 fold 和 stage 宏平均均要求 compatibility@90 `>=.90`、ICE `<=.10`、mean width 和 WIS 都严格小于基线；相等、NaN、无训练/测试有限行或不可比较均 FAIL。

结果每个 `(stage_id,fold_id,physical_cell_id,α)` 一行，字段固定为 `n_finite, compatibility_coverage, enclosure_coverage, mean_width, median_width, weighted_interval_score, empirical_enclosure_coverage, right_censored_n, right_censored_lower_bound_violation_rate, baseline_*`；另输出逐 cell/fold 等权的 stage 宏平均行，禁止微平均。

### 四类复验 RED 清单

1. **映射/实体**：After-SOH80 未进入 MappingAudit、required-role matrix 无官方 provenance、60-cell inventory 不可证明、同一文件跨 cell/阶段/角色复用或反向映射不一致 -> whole-version INVALIDATED。
2. **删失端点/路由**：`a=100,b=150,t=40 -> RUL=[61,110]`；`t=101` 拒绝；right censor `c=150,t=40 -> [111,+∞)` 且 `training_eligible=false`；file-end、left、invalid 不得进入有限监督。
3. **指标/嵌套/分母**：`Y1=[4,6],Y2=[10,12]`，P90=`[3,7],[11,13]` -> compatibility=1、enclosure=.5、mean/median width=3、WIS=3；enclosure(.5,1,1) -> ICE=.10。`Y=[4,6],P90=[7,9]` -> WIS=4；right censor lower=8、P90 upper=7 -> violation=1，并从有限分母排除；非嵌套必须 FAIL。
4. **LOCO 基线/可比性**：训练 `[2,4],[4,6],[8,10],[10,12]` 在 α=.5 得 baseline `[2,10]`；模型 `[3,7]` 严格胜出，等于 `[2,10]` 为 tie FAIL；`m=0`、空有限 fold、NaN 或分母不一致均 NOT_COMPARABLE/FAIL。

## 审批链

每个可验收节点先提交测试工程师线程 `019fd634-ccff-78b0-a77f-734823a5cd57`。未经其明确 PASS，不向总工程师申请数据版本、训练或完成批准。即使数据版本通过，`interval_training_authorized` 仍保持 false，真实训练另行审批。

详细设计：`docs/superpowers/specs/2026-08-06-mendeley-knee-interval-rul-design.md`  
详细 TDD 计划：`docs/superpowers/plans/2026-08-06-mendeley-knee-interval-rul.md`
