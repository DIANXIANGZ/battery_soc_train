# SOC/SOE/SOH/SOT 独立候选重建实施前执行包

日期：2026-08-09（Asia/Shanghai）  
阶段：方案 A，实施前只读送测  
状态：四目标均 `PLAN_PENDING`；本文件不是来源准入、实现许可、检查点 1 PASS、烟雾许可或训练许可。

## 1. 独立判断与实施顺序

已确认事实：

- 旧 A123 SOC 派生表使用完整循环 `min/max net_range`，存在未来泄漏，固定为不可复用 `FAIL`。
- 旧 NASA 五状态表及生成链含 `rul_cycles`，固定为不可复用 `FAIL`，不能删列绕过。
- `public_battery_corpus_v9`、`v10` 全体 `INVALIDATED`；RUL、v11、生命周期、EOL、trajectory 资产均不进入本方案的读取、生成、准入或运行链。
- 当前没有任何目标满足“来源证据、目标独立生成链、角色、严格留出、因果标签”全部条件。

拟议顺序只在本执行包测试 PASS 且获得实现授权后适用：

1. 共用只读 CALCE 原始解码层的来源/许可/cell-condition 可分性门禁；失败则 SOC、SOE、SOT 同时停在来源阶段，但三者仍分别出具 blocker。
2. SOC 独立生成器与独立 admission。
3. SOE 独立生成器与独立 admission；只与 SOC 共享原始测量读取，不共享标签、manifest、授权、配置、导出或结果。
4. SOT 独立生成器与独立 admission。
5. SOH：只有获得另一个现成本地、明确许可、非 RUL/EOL/trajectory 的逐循环容量来源后才开始；当前直接阻断，不复用 MATR/NASA 生命周期资产。

## 2. 全局不可绕过合同

### 2.1 目标独立性

每个目标拥有独立 builder、canonical schema、manifest、admission capability、配置、检查点报告与结果根目录。共享层仅允许返回原始、无标签测量与不可变身份字段；禁止返回或计算其他目标、RUL、EOL、trajectory、split 或授权状态。

零容忍 token 扫描只作用于可能携带数据或语义的内容面：archive member 的**逻辑数据相对路径**；候选 manifest/lineage 内的源实体字段（包括 source/member/file/dataset/parent artifact 标识与路径）；canonical 列名；target/feature/authorization 元数据。上述内容面对下列大小写不敏感 token 必须 0 命中：`rul`、`rul_cycles`、`rul_observed`、`eol`、`eol_*`、`eol_provenance`、`trajectory`、`trajectory_*`。命中即整个目标候选 `FAIL`；禁止删列后继续。

项目代码目录、测试目录、配置目录、候选输出根和结果根不作 `rul` 子串扫描；它们可能使用 `non_rul` 或 `非RUL` 作为隔离命名。外部资产路径采用下一节的规范化精确 denylist 根匹配，不能用目录名任意位置的子串命中替代根绑定判断。

### 2.2 来源与失效资产拒绝

唯一闭合台账为 `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json`，版本 `2026-08-09.p0-2.1`，SHA-256 `44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`，共 13 个规范根。台账逐项给出规范化绝对根、资产类别、冻结状态与证据路径，覆盖 NASA RUL 混合原始/训练资产、MATR、Oxford、区间 RUL archive、生命周期、public corpus 总根（包含 v9/v10 INVALIDATED 与 v11）、质量报告总根、历史 NASA 五状态/RUL 结果、strict smoke 结果和 v11 临时证据根。拒绝集合只以该台账的 `entries[].canonical_root` 为定义。

未来唯一加载接口为 `load_frozen_asset_denylist(path: Path, expected_sha256: str) -> FrozenAssetDenylist`；它必须先复算实体 SHA、验证 ledger/version/status、13 个绝对根唯一且 `unknown_external_root_policy=FAIL_CLOSED`，再返回不可变规范根集合。SHA、schema、条目缺失/重复或相对路径均必须在 archive/member 数据读取前失败。external source root 只有两种可识别状态：命中本 denylist 时拒绝；命中独立、已批准且 capability 绑定的 source allowlist 时才可继续。两者均不命中的未知 root 也 fail-closed。当前 CALCE 尚未进入 source allowlist，因此仍 `NOT_ADMITTED`。所有目标的拟议检查点命令只能通过同一组选项加载台账：`--denylist /Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json --denylist-sha256 44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`；禁止目标自带或内联另一份拒绝集合。

全量拒绝扫描必须在读取任何 archive member 前完成。先对路径执行 `resolve(strict=False)`、Unicode NFC、路径分隔符规范化；再判断 source/archive/member 的实际实体是否等于台账内 `canonical_root` 或位于其后代。文件根只精确匹配该文件。manifest lineage 不得引用这些规范根、其后代或台账未来登记的实体哈希；任一命中立即 fail-closed。项目根、测试根、配置根、全新的候选输出根和结果根不是 candidate external source，不参与外部根匹配，仅因名称含 `non_rul`/`非RUL` 不得拒绝。

门禁最小可证伪用例（仅规划，未运行）：

- **RED：真实语义命中必须拒绝。** archive member 为 `cells/rul_cycles.csv`，或 lineage 的 `source_path` 指向已规范化的 RUL/v11 denylist 后代，或 canonical 列/feature/target/authorization 含 `rul_cycles`、`eol_provenance`、`trajectory_*` 时，预期整个目标 `FAIL`；删除输出列后重试仍必须 `FAIL`。
- **RED：闭合台账失败必须拒绝。** 候选声明一个不在台账中的 external source root、台账漏项/条目数不是 13、台账 SHA 不符，或 source 命中台账内任一 `canonical_root`/其后代时，预期在读取 archive member 前 `FAIL`；不得自动扩充台账、猜测类别或按目标放行。
- **GREEN：隔离目录名不得误拒绝。** 项目根为 `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/src/data_processing/non_rul/`，候选根为 `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/soc_v1/`，但 archive member 逻辑路径、lineage 源实体字段、canonical 列和 target/feature/authorization 元数据均无禁用 token，且 source 不在精确 denylist 根下时，预期零容忍/路径门 `PASS`（其他门仍独立裁定）。

### 2.3 严格留出

候选主键统一为 `(source_id, physical_cell_id, condition_id, session_id, cycle_id, timestamp_or_sample_index)`；必须唯一且非空。`cell_id` 与 `condition_id` 同时参与外层严格分组：测试 cell 在训练/验证中为 0 行，测试 condition 在训练/验证中为 0 行；若数据的 cell 或 condition 基数不足以形成非空 train/validation/test，目标即 `PLAN_BLOCKED`，不得退化为随机行切分。任何归一化、特征选择、插补和超参数拟合只能使用当前外层训练组。

## 3. SOC

**当前状态：`NOT_VERIFIABLE / PLAN_BLOCKED`。**

1. **现有来源证据。** 拟用四个本地 CALCE A123 dynamic archive：
   - `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_0c/download_manifest.json` → archive SHA-256 `c18df3909de27c4409d5e9730c5078284f3883ee52193b559ca8e0ee17732505`，版本文字 `CALCE A123 archive, accessed 2026-08-03`；
   - `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_25c/download_manifest.json` → `b7e5402815b491f4052e1fc02ac12723a28a6893e3f695f10a39b773043145f2`；
   - `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_50c/download_manifest.json` → `7fae05b50c7f4edcc799a7d817d56fb701e1e8894b538e043d05d08ab60f91bc`；
   - `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_temperature/download_manifest.json` → `1753bbf603baf54388ea2fee28f3be00c082e525515efb2074f362f335988604`。
   这些 manifest 写有 `Research/publication use with CALCE database and article attribution`，但当前没有独立、版本固定的许可条款快照可定位，因此许可证门为 `NOT_VERIFIABLE`，不得称“现有合规来源”。
2. **既有 manifest/admission。** 仅有上述 download manifest；没有 SOC 独立 canonical manifest 或有效 admission capability，状态 `NOT_ADMITTED`。不得写入或补造。
3. **因果标签合同。** `soc(t)=clip(soc_anchor + integral_[anchor,t](eta*I(tau)d tau)/Q_ref,0,1)`。`soc_anchor` 必须来自当前 session 开始前已知协议状态；`Q_ref` 只能来自该 cell 当前 session 前已完成且获准的容量校准。禁止当前完整循环 min/max、循环终点容量、未来电流或后验重置。
4. **allowlist/角色。** 原始共享层只允许 `source_id, physical_cell_id, condition_id, session_id, cycle_id, timestamp_s, voltage_v, current_a, temperature_c, protocol_step`。SOC 独立层可新增 `soc`、`soc_anchor`、`capacity_reference_ah`、`label_reference_time`；这些引用列不得作为学习特征。角色列不得与目标或 feature 重叠。
5. **留出。** 外层 `(physical_cell_id, condition_id)` 双重未见组；内层仅在剩余 cell/condition 上确定性分组。当前 archive 的物理 cell 数和 condition 映射尚无已准入证据，故不可执行。
6. **只读因果审计。** 未来尾段电流/电压/温度扰动后，扰动点之前的 `soc`、reference 与主键逐位不变；改变同循环终点不得改变前缀标签；按 lineage 检查引用时间 `<= prediction_time`。
7. **RED 与检查点命令（仅拟议，未运行）。** RED：完整循环 extrema 使前缀改变时拒绝；缺 `cell_id/condition_id` 拒绝；跨 cell/condition split 重叠拒绝；任一禁用 token/路径拒绝；缺许可快照或 SHA 不符拒绝。拟议命令：`python -m pytest -q tests/non_rul/test_soc_candidate_contract.py`，再运行 `python -m src.evaluation.precheck_non_rul_target --target soc --candidate <soc_manifest> --denylist /Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json --denylist-sha256 44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`；预期只有所有门均 PASS 才生成检查点报告。
8. **拟议产物/回滚。** builder `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/src/data_processing/non_rul/build_soc_candidate.py`；测试 `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/tests/non_rul/test_soc_candidate_contract.py`；候选根 `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/soc_v1/`；配置 `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/configs/non_rul/soc_v1.json`；结果根 `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/04_非RUL独立训练/soc_v1/`。回滚点是 SOC RED 测试通过前不创建任何候选目录；实现失败仅撤销本目标新增代码/配置与全新的 `soc_v1` 目录，不触碰共享原始 archive 或历史产物。

## 4. SOE

**当前状态：`NOT_VERIFIABLE / PLAN_BLOCKED`。**

1. **来源/许可/version/hash。** 与 SOC 共享上述四个 CALCE 原始 archive 和 download manifest，但不共享任何派生物。相同的独立许可快照缺口使来源仍 `NOT_VERIFIABLE`。
2. **既有 manifest/admission。** 没有 SOE 独立 canonical manifest 或 admission，状态 `NOT_ADMITTED`。未来 manifest 路径必须独立于 SOC。
3. **因果标签合同。** `soe(t)=clip((E_anchor + integral_[anchor,t](eta*V(tau)I(tau)d tau))/E_ref,0,1)`；积分方向、采样时间单位和充放电效率须由协议固定。`E_anchor/E_ref` 只能来自 prediction time 前已完成的独立校准，禁止本循环完整能量、终点能量、未来电压/电流或由 SOC 标签反推。
4. **allowlist/角色。** 共享读取层 allowlist 与 SOC 相同；SOE 独立层只新增 `soe, energy_anchor_wh, energy_reference_wh, label_reference_time`。SOC/SOE 的 label、manifest、admission、配置、导出和结果路径必须互不引用。
5. **留出。** 与 SOC 相同的 cell/condition 双重严格留出，但必须在 SOE 自己的 manifest 中重算和绑定；不得引用 SOC admission。当前 cell/condition 基数未核验，阻断。
6. **只读因果审计。** 扰动未来 `V/I` 不得改变前缀 SOE；秒/分钟单位的解析必须有解析器级反例；同循环终点变化不得改变前缀 reference。
7. **RED/命令。** RED：完整循环 energy normalization、时间单位错配、SOC 派生依赖、跨目标 manifest 引用、禁用 token、split 重叠、缺许可或哈希不符均拒绝。拟议命令：`python -m pytest -q tests/non_rul/test_soe_candidate_contract.py`；`python -m src.evaluation.precheck_non_rul_target --target soe --candidate <soe_manifest> --denylist /Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json --denylist-sha256 44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`。
8. **产物/回滚。** `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/src/data_processing/non_rul/build_soe_candidate.py`、`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/tests/non_rul/test_soe_candidate_contract.py`、`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/soe_v1/`、`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/configs/non_rul/soe_v1.json`、`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/04_非RUL独立训练/soe_v1/`。SOE 失败仅删除本目标全新产物并使其 admission 失效，不动 SOC 或共享 raw archive。

## 5. SOH

**当前状态：`FAIL / PLAN_BLOCKED`。**

1. **来源证据。** 当前未找到满足“现成本地实体 + 明确版本化许可 + 非 RUL/EOL/trajectory 来源链 + 多 cell/condition 逐循环容量”的来源。`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/02_Stanford_LFP_SOC_2025/raw/` 只有 `README.md` 与 `LICENSE`，没有数据实体；该 LICENSE 是否覆盖数据本身也未独立裁定。MATR、NASA 生命周期、v11 均属明确冻结资产，不列为候选。
2. **manifest/admission。** 不存在 SOH 合格 source/download manifest、canonical manifest 或 admission；状态 `NOT_ADMITTED`。
3. **标签合同。** 若未来获准来源，`soh(c)=Q_discharge_completed(c)/Q_reference`，prediction time 是本次完整容量测试结束后；`Q_reference` 必须是额定容量或该 cell 在预测循环前固定的首个合格基准，且一经设定不随未来循环更新。禁止未来容量、EOL 阈值、寿命终点、剩余循环或 trajectory 派生量。
4. **allowlist/角色。** `source_id, physical_cell_id, condition_id, session_id, cycle_id, cycle_end_time, capacity_ah, capacity_reference_ah, soh`；`capacity_ah/capacity_reference_ah` 是标签证据，不进入学习 feature allowlist。特征另行只允许 prediction time 前完成的电压/电流/温度/时长统计。
5. **留出。** cell/condition 双重严格留出；同一 physical cell 的所有 cycle 必须处于同一外层角色。无来源，当前不可验证。
6. **只读因果审计。** 改写未来 cycle 容量不得改变历史 SOH；固定 reference 不得随未来追加数据改变；循环必须单调、唯一且来源协议可定位。
7. **RED/命令。** RED：file-end/EOL/RUL/trajectory 来源、未来 reference、同 cell 跨折、缺容量单位/周期身份、来源实体缺失均拒绝。拟议命令：`python -m pytest -q tests/non_rul/test_soh_candidate_contract.py`；`python -m src.evaluation.precheck_non_rul_target --target soh --candidate <soh_manifest> --denylist /Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json --denylist-sha256 44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`。来源缺口解除前这些命令不得运行。
8. **产物/回滚。** 仅占位规划：`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/src/data_processing/non_rul/build_soh_candidate.py`、`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/tests/non_rul/test_soh_candidate_contract.py`、`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/soh_v1/`、`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/configs/non_rul/soh_v1.json`、`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/04_非RUL独立训练/soh_v1/`。当前回滚点为“不创建任何 SOH 文件”。

## 6. SOT

**当前状态：`NOT_VERIFIABLE / PLAN_BLOCKED`。**

1. **来源/许可/version/hash。** 拟用上述四个 CALCE archive，特别是 0/25/50/N10 条件；独立许可快照和 cell/condition 基数仍缺失，因此来源 `NOT_VERIFIABLE`。
2. **manifest/admission。** 没有 SOT 独立 manifest/admission，状态 `NOT_ADMITTED`。
3. **标签合同。** 采用已确定的固定未来 300 秒定义：`sot_5min_c(t)=temperature_c(t')`，其中 `t'` 是同一 cell/session/cycle 中首个 `timestamp >= t+300s` 的观测；输入只允许 `<=t` 的前缀。无同循环未来点则该样本不产生标签，禁止跨 cycle/session 查找、插值到未来或把当前温度同时作为目标与泄漏特征。
4. **allowlist/角色。** 共享 raw allowlist 与 SOC 相同；SOT 独立层仅新增 `sot_5min_c, target_timestamp_s, horizon_s=300`。当前温度可作为 t 时刻可观测输入，但 `target_timestamp_s` 的温度不得进入 feature。
5. **留出。** cell/condition 双重严格留出；温度 condition 必须保留物理设定，不得由目标温度事后分箱。当前 cell 基数未证实，阻断。
6. **只读因果审计。** 未来尾段扰动不改变此前 feature；标签必须精确指向同组的首个 `>=300s` 点；跨 cycle/session 的近邻匹配必须拒绝；所有归一化仅训练折拟合。
7. **RED/命令。** RED：同刻温度身份标签、跨 cycle 匹配、未来温度进入 feature、后验温度分箱、禁用 token、split 重叠、许可/hash 缺失均拒绝。拟议命令：`python -m pytest -q tests/non_rul/test_sot_candidate_contract.py`；`python -m src.evaluation.precheck_non_rul_target --target sot --candidate <sot_manifest> --denylist /Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json --denylist-sha256 44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`。
8. **产物/回滚。** `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/src/data_processing/non_rul/build_sot_candidate.py`、`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/tests/non_rul/test_sot_candidate_contract.py`、`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/sot_v1/`、`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/configs/non_rul/sot_v1.json`、`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/04_非RUL独立训练/sot_v1/`。失败仅失效并删除本目标全新版本，不触碰其他目标或 raw archive。

## 7. TDD、检查点 1 与运行审批顺序

本包 PASS 后仍需单独实现授权。每个目标严格串行：先 RED 并记录预期失败，再最小实现 GREEN，再运行该目标检查点 1。检查点 1 必须重新核对 source/license/version/hash、目标独立 lineage、allowlist、主键、cell/condition split、未来扰动、RUL 零命中、v9/v10/v11/RUL 路径拒绝；任一失败即停止该目标，原子失效其 admission，不推进烟雾。

拟议最小烟雾（只有该目标检查点 1 获测试 PASS 且上层批准后）：只验证数据加载、一个 fold、极小 epoch/iteration、产物隔离和 fail-closed；不声称性能通过。正式验收必须覆盖所有严格外层 cell/condition fold、训练折内预处理、逐 fold/逐 cell/逐 condition 指标及无泄漏复核；烟雾和正式训练继续分别审批。

## 8. XGBoost 与 Torch 隔离合同

若后续某目标选择 XGBoost，只允许独立、无 Torch 的 worker；不得由已导入 torch/libtorch 的平台进程内调用。拟议解释器为 `/opt/homebrew/bin/python3.12`，但其依赖集合当前未验证，故状态 `NOT_VERIFIABLE`。

批准后才可运行的静态/启动前合同：

- worker 入口不得 import `torch`、`pytorch` 或任何会传递导入它们的训练模块；`sys.modules` 中 `torch` 为 0；
- 启动前记录 `python --version`、`xgboost.__version__`、解释器绝对路径与依赖锁定清单；
- 原生映像中 `libtorch`、`libc10` 为 0，`libomp` 只能有一个唯一实体/UUID；
- worker 在创建运行目录和拟合前验证目标 admission capability；非零退出、SIGSEGV、重复 OpenMP 或绑定异常立即停止，不重试真实拟合；
- 拟议验证命令：`PYTHONNOUSERSITE=1 /opt/homebrew/bin/python3.12 -m src.training.xgboost_isolation_probe --require-no-torch --require-single-openmp`；拟议训练形态：`PYTHONNOUSERSITE=1 /opt/homebrew/bin/python3.12 -m src.training.xgboost_worker --capability <target-capability>`。两条均未运行，也不构成许可。

## 9. 本次边界与送测结论

本执行包的验收对象是计划完整性，不是四目标数据准入。当前逐目标结论：

| 目标 | 执行包状态 | 技术准入 | 主要缺口 |
|---|---|---|---|
| SOC | `PLAN_PENDING` | `NOT_VERIFIABLE / PLAN_BLOCKED` | CALCE 许可快照、cell/condition 可分性、独立 manifest/admission |
| SOE | `PLAN_PENDING` | `NOT_VERIFIABLE / PLAN_BLOCKED` | 同上；另需独立能量 reference 合同验证 |
| SOH | `PLAN_PENDING` | `FAIL / PLAN_BLOCKED` | 没有现成合规、非 RUL 的本地逐循环容量实体 |
| SOT | `PLAN_PENDING` | `NOT_VERIFIABLE / PLAN_BLOCKED` | CALCE 许可快照、cell/condition 可分性、300 秒同组标签可用性 |

本次只新增本 Markdown 执行包；未读取训练样本，未新建或写入 manifest，未修改代码、配置或数据，未启动 TDD/检查点命令、烟雾或训练。测试工程师明确 PASS 与上层实现授权到达前，保持冻结。
