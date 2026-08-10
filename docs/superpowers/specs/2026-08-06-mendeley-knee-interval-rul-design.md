# Mendeley Knee V4 区间删失 RUL 设计

日期：2026-08-06  
状态：方案已批准；仅设计，尚未下载、实现或训练。

## 目标与非目标

新增一个独立的 `interval_rul` 任务，以 Mendeley Data `zn82y35zr8` Version 4、DOI `10.17632/zn82y35zr8.4`、CC BY 4.0 为唯一候选来源。任务预测 EOL 所在的物理循环区间，不预测单一 EOL cycle。

严格点 RUL 合同继续冻结：v11、MATR、Oxford、NASA 不进入新任务；`MAE <= 1 cycle`、`rul_cycles` 点标签和“精确 RUL”措辞均不得用于新区间任务。新区间任务通过数据门禁也不自动授权烟雾或训练。

## 方案选择

采用独立数据域：`src/interval_rul/`、独立 manifest、独立 canonical table、独立评估器和独立结果目录。拒绝两种替代方案：

1. 扩展 v11：会改变冻结数据版本，并可能使点标签消费者误读区间标签；
2. 仅扩展自定义训练字段：缺少来源级 EOL/censoring 合同，无法在命令启动前证明标签合法。

## 任务与标签合同

阶段必须独立：

- `soh100_to_80`：从 BOL 到官方 SOH80 EOL；
- `soh80_to_60`：从 SOH80 后重新开始的第二寿命阶段到官方 SOH60 EOL。

两阶段分别建表、分别切分、分别评估。`physical_cell_id` 可相同，但任何模型、归一化器、特征选择、早停或指标不得跨阶段共享。下载后必须从官方说明确认 SOH80/SOH60 的容量参考基准；若基准不明确，阶段门禁失败，不自行假定均相对 BOL。

对某一阶段，令 `a` 为最后一次严格高于阈值的 RPT 物理循环，`b` 为第一次小于等于阈值的 RPT 物理循环。物理 EOL 满足 `(a, b]`。因循环号为整数，canonical EOL 区间存为闭区间 `[a+1, b]`。

在预测循环 `t <= a`：

```text
rul_lower_cycle = a - t + 1
rul_upper_cycle = b - t
lower_inclusive = true
upper_inclusive = true
```

只有 `a < b`、循环号连续语义明确且 `rul_lower_cycle <= rul_upper_cycle` 才生成有限区间标签。预测样本不得来自 `(a,b]` 或 EOL 之后。

删失类型：

- `interval_observed`：同时存在 last-above 与 first-at-or-below，允许有限区间监督；
- `right_censored`：仅知最后一次仍高于阈值的循环 `c`，RUL 为 `[c-t+1, +∞)`；合同只允许未来另行验收的显式删失感知损失使用，v1 中 `training_eligible=false`，只审计下界违例，不伪装有限区间；
- `left_censored`：首个有效 RPT 已在阈值以下；只进入 `censoring_audit.csv`，本版本不生成训练标签；
- `invalid_protocol`：cell/阶段映射、阈值基准、循环号或终止语义不明；完全阻断。

RPT cadence 以逐电芯实测差分记录，同时在 manifest 报告 min/median/max；公开元数据给出的 50–100 cycles 仅作预期范围，不能覆盖真实文件审计。

## Canonical schema 与隔离

独立标签表至少包含：

```text
source_id, source_version, source_sha256, license_id,
physical_cell_id, stage_id, condition_id, prediction_cycle,
last_above_cycle, first_at_or_below_cycle,
rul_lower_cycle, rul_upper_cycle, censoring_type,
lower_inclusive, upper_inclusive, threshold_soh,
threshold_reference, rpt_cadence_cycles, label_provenance
```

有限区间训练标签表只含 `interval_observed`；`rul_lower_cycle`、`rul_upper_cycle` 均为整数。`right_censored`、`left_censored` 与 `invalid_protocol` 进入 `censoring_audit.csv`；v1 不把 right-censored 行转成中点、有限上界或点标签，也不用于有限区间损失，只报告下界违例。后续若要用于训练，必须另行设计并验收显式 censored likelihood。`stage_id` 只能取两个固定值。`source_id` 固定为 `mendeley_knee_v4_interval_rul`。输出目录建议为数据中心新的 `05_区间删失RUL规范数据/mendeley_knee_interval_rul_v1/`；不得使用 `public_battery_corpus_v12` 命名，也不得覆盖 v11。

manifest 必须记录固定 DOI、许可全文/URL、记录 HTML 指纹、官方文件名、Content-Length、ETag/Last-Modified、下载 UTC、最终 URL、下载实体 SHA-256、解析器版本、阶段计数、四类 censoring 的 cell/row 数、`valid_for_interval_training` 和 `interval_training_authorized`。两项授权初始均为 false；数据门禁通过只允许前者变 true，训练授权仍需单独批准。

### 文件 inventory 的双向合同

canonical manifest 顶层必须包含：`schema_version`、固定 source/version/DOI/license、许可与记录快照 SHA-256、archive 官方名/字节/SHA-256、final URL/Content-Length/ETag/Last-Modified/UTC、parser version、physical cell count、`artifacts[]`、`mapping_audit`、逐阶段 censoring 计数和两个 false 授权字段。下载前未知的实体字段不得用空字符串假装确认。

`artifacts[]` 每行固定为：

```text
artifact_id, archive_member_path, member_sha256, member_bytes,
official_cell_token, physical_cell_id, stage_id, artifact_role,
protocol_reference_id, cycle_index_semantics, threshold_reference,
mapping_provenance
```

`artifact_role ∈ {cycle,rpt,after_soh80}`。`artifact_id=sha256(archive_sha256+"\0"+exact_archive_member_path)`；规范化路径另设唯一约束。正向函数 `F(artifact_id)->(physical_cell_id,stage_id,artifact_role)` 必须单值；逆向索引 `G(cell,stage,role)->ordered set[artifact_id]` 必须无重复，且 `F(G(...))` 全部回到原三元组。

可测试接口固定为：

```text
inventory_archive(root, source_manifest) -> ArtifactInventory
validate_bidirectional_mapping(inventory, required_roles_by_stage) -> MappingAudit
```

`MappingAudit` 必须对每个 `(cell,stage)` 输出 `cycle_artifact_ids`、`rpt_artifact_ids`、`after_soh80_artifact_ids`，以及集合 C/R/A、missing/duplicate/cross-cell/cross-stage 列表和 `valid`。adapter 不得只返回 Cycle/RPT 而漏掉 After-SOH80。

每阶段必需角色、每角色文件基数和 After-SOH80 的权威阶段归属，必须由下载后的 V4 随包说明/实体清单生成 `required_roles_by_stage` 并记录 provenance；当前设计不猜测“每 cell 各一个文件”。该矩阵缺失、任一官方要求集合不完整、60-cell 名单不能从实体证明、token 归一化碰撞、同一 artifact/path/content 跨 cell/阶段/角色复用、正反映射不互逆或 cycle-range chunk 重叠，整个版本写 `INVALIDATED.json`。

## 数据与泄露门禁

下载后准入必须全部通过：

1. 版本/许可：V4、DOI 和 CC BY 4.0 与本地许可快照一致；
2. 实体：官方文件名、字节数、响应指纹和本地 SHA-256 完整；
3. 身份：60 个物理电芯的目录/文件映射唯一，无重复、缺失或跨 cell 拼接；
4. 协议：每阶段阈值、容量参考、cycle index、RPT 类型和终止状态可追溯；
5. 区间：端点整数、`a < b`、宽度与实际 RPT cadence 一致；file-end 不得自动成为 `b`；
6. 因果：预测循环 `t` 的特征只来自 `<=t`；对未来尾段作扰动不得改变任何前缀特征、split 或 normalization；
7. 隔离：LOCO 外折按 `physical_cell_id`，测试 cell 不参与归一化、特征选择、超参或早停；两个阶段分别运行；
8. 来源：MATR/Oxford/NASA 行数必须为 0，v11 哈希保持不变。

任一门禁失败，写 `INVALIDATED.json`，保持所有授权 false，不叠加修复或启动训练。

## 预测输出、验收指标与确定性基线

有限标签为 `Y=[L,U]`；right-censored 标签只有整数下界 `L`。模型对每个有限行和名义水平 `α∈{0.50,0.80,0.90}` 输出闭实数区间 `Pα=[lα,uα]`。三层必须满足 `l90<=l80<=l50<=u50<=u80<=u90`。缺失、非有限、端点倒置、不嵌套或 fold 无有限行，使该 `(stage,fold)` 为 `NOT_COMPARABLE` 并 FAIL。

结果 schema 每个 `(stage_id,fold_id,physical_cell_id,α)` 一行：`n_finite, compatibility_coverage, enclosure_coverage, mean_width, median_width, weighted_interval_score, empirical_enclosure_coverage, right_censored_n, right_censored_lower_bound_violation_rate, baseline_*`，另产生 cell/fold 等权的 stage 宏平均行；禁止按样本行数微平均。

对有限标签 `Y=[L,U]` 和预测 `P=[l,u]`：

```text
C = 1[max(L,l) <= min(U,u)]
E = 1[l <= L and U <= u]
W = u - l
D = max(L-u, l-U, 0)
WIS = W + 2D
```

cell/fold 内 coverage、mean width、WIS 取算术均值；median width 为普通中位数。right-censored 行不进入这些分母，只报 `V=1[u90<L]` 和 violation rate；`u90` 缺失/非有限即 fail-closed。校准固定使用 enclosure：`ECα=mean(Eα)`，`ICE=mean_α|ECα-α|`。每个 fold 及 stage 宏平均均要求 `compatibility@90>=0.90`、`ICE<=0.10`。

每个 `(stage,LOCO fold)` 的非训练基线只取训练 cells 的 `interval_observed` 行。令下端点集合 `{L_i}`、上端点集合 `{U_i}`、`m>=1`；nearest-rank 分位数为 `Q_p(x)=x_(max(1,ceil(mp)))`（升序、1-based）。令 `q=(1-α)/2`：

```text
Bα = [Q_q({L_i}), Q_(1-q)({U_i})]
```

基线是该 fold/stage 的常量嵌套区间，不读取测试 cell、测试标签、测试特征或模型输出。模型在每个可比 fold 及 stage 宏平均上必须同时满足 `mean_width_model < mean_width_baseline` 与 `WIS_model < WIS_baseline`；相等、NaN、无训练/测试有限行或口径不一致均为 `NOT_COMPARABLE` 并 FAIL。right-censored 只报告下界违例，不参与“优于基线”。

模型验收只使用区间指标，并按阶段、外层 LOCO fold 和 cell 报告：

- `interval_compatibility_coverage`：预测区间与标签可行区间有交集的比例；
- `interval_enclosure_coverage`：预测区间完整包含标签可行区间的比例；
- `mean_prediction_interval_width_cycles` 与 `median_prediction_interval_width_cycles`；
- `weighted_interval_score`：按上述 `WIS=W+2D` 公式，越低越好；
- `interval_calibration_error`：在 50%、80%、90% 名义区间下，enclosure coverage 与名义覆盖率绝对差的宏平均；
- right-censored 样本单独报告 lower-bound violation rate，不与有限区间混合平均。

结构验收要求 100% schema/因果/阶段/LOCO 门禁通过。模型质量按上一节的 compatibility、enclosure calibration、宽度与 WIS 联合规则判定。所有阈值必须给出逐 cell 和宏平均，不允许用微平均掩盖失败 fold。

禁止报告点 MAE、点 accuracy、`<=1-cycle` 或“曲线完全贴合”。如果预测区间只靠扩大宽度获得覆盖，宽度与 interval score 会使其无法通过。

## 四类 RED 复验清单

1. **映射/实体**：After-SOH80 未进入 `MappingAudit`、required-role matrix 无官方 provenance、60-cell inventory 不可由实体证明、缺失/重复/token 碰撞/跨 cell/跨阶段/跨角色复用或 `F/G` 不互逆，均使 whole-version `INVALIDATED`。
2. **删失端点/路由**：`a=100,b=150,t=40` 必须生成 `[61,110]`；`t=101` 拒绝；right censor `c=150,t=40` 只能生成 `[111,+∞)` 且 `training_eligible=false`；file-end 不得成为 EOL，left/invalid 不得进入训练或有限指标分母。
3. **指标/嵌套/分母**：固定手算向量必须得到 compatibility、enclosure、width、`WIS=W+2D` 与 ICE 的约定值；非嵌套、缺失/非有限端点 fail-closed；right-censored 只进入下界违例分母，不进入有限 coverage/width/WIS/calibration。
4. **LOCO 基线/可比性**：基线只能使用同 stage/fold 的训练有限行并按 nearest-rank 生成常量区间；`m=0`、空测试有限行、NaN、分母不一致、模型与基线并列或任一 width/WIS 未严格更小，均为 `NOT_COMPARABLE`/FAIL。

## 下载准入与失败策略

拟请求的唯一实体是官方 V4 记录中的 `Battery raw data.zip`，页面显示约 1.38 GB。入口固定为 `https://data.mendeley.com/datasets/zn82y35zr8/4`；不得猜测 file API URL。只有得到下载批准后，才可从该公开页面的可见文件入口解析实际 URL。

下载前再次固定 V4/DOI/CC BY 4.0。仅接受无登录、无 OAuth、公开 2xx 的官方请求；若出现 401/403/429、TLS 失败、非 2xx、访问限制或无法解释的重定向，立即停止，不重试、不使用镜像。正常官方跳转也必须记录完整链路，并确认仍由 Mendeley 官方记录发起且不要求认证；否则不读取响应体。

下载后记录 Content-Length、ETag、Last-Modified、UTC 和 SHA-256。若记录没有发布上游 checksum，本地 SHA-256 只作为后续再现指纹，不冒充发布者校验；来源真实性同时依赖固定 DOI、TLS 官方入口和响应链证据。

## 回滚与失效

所有新产物位于独立目录。失败时只将新区间版本标记为失效，不删除证据、不触碰 v11。原始压缩包只读保存；解析产物可通过新版本目录重建，不原位覆盖。adapter/schema/指标合同任何变动都使既有 admission capability 失效，需要重新跑全部门禁。
