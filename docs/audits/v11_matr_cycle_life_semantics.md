# v11 MATR Batch1 `cycle_life` 语义审计

审计日期：2026-08-04  
审计范围：只读取证；未修改 adapter、schema、模型、数据版本或阈值，未运行烟雾/正式训练。  
状态：`v11.valid_for_training=false`，本报告不构成训练授权。

## 结论

1. 原始 Batch1 MAT 中的 `cycle_life` 数字本身不能证明已观测 EOL。46/46 个电芯均满足 `stored_cycle_life = raw_cycle_count + 1`，其中包括官方明确说明“在到达阈值前终止”的 5 个电芯。
2. 官方标签生成代码没有对逐循环容量作平滑。其规则是：只有末次 `QDischarge < 0.88 Ah` 时才取首次低于 0.88 Ah 的索引；否则直接取 `cycles 数量 + 1`。
3. Batch1 struct 缺少真实 cycle 1；`QDischarge` 首槽为 0，不能当作容量阈值穿越。排除该缺失槽后，46/46 个电芯均没有实测 `<0.88 Ah` 穿越。
4. 36 个非续接、非已知早停电芯的末次容量为 0.8800565-0.88336319 Ah；5-cycle 尾部中位数为 0.88114411-0.88594258 Ah。它们是“略高于 0.88”的官方 `n+1` 标签，不是实测 crossing。
5. 这 36 个电芯全部逐条出现在论文 Supplementary Table 9，表中 cycle life 与原始 MAT 的 `n+1` 值 36/36 完全一致；5 个官方已知早停电芯全部未出现在该表，并被 `LoadData.m` 明确剔除。因此：
   - 单独的 MAT 字段不够；
   - “Supplementary Table 9 正式列入 + MATR Batch1 数据说明明确早停集合 + `LoadData.m` 剔除同一集合 + 数值逐项一致”的联合证据，足以把这 36 个电芯识别为 `official_cycle_life_eol` 候选；
   - 在批准修改 provenance 前，v11 中这 36 个电芯仍保持 `right_censored`。

## 官方来源链

| 来源 | 固定标识 | 相关事实 |
|---|---|---|
| MATR Batch1 struct | file `5c86c0b5fa2ede00015ddf66`; 3,025,320,241 bytes; SHA-256 `9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba` | 46 个 Batch1 电芯、逐循环 `QDischarge`、stored `cycle_life` |
| MATR Batch1 页面/API | project `5c48dd2bc625d700019f3204`; batch `5c86c0b5fa2ede00015ddf67` | 试验目标 0.88 Ah；cycle 1 因采样率过高未进入 struct；channels 1/2/3/5/6 续接；channels 13/19/21/22/31 提前终止 |
| 官方 GitHub `LoadData.m` | repo commit `1ef13d27c66dc3d73affdaa008fbeba5687b2ea4`; file SHA-256 `7914333f0a963a0742d9fff340f1d4bc2ad912f1b04a236b3ae6c39fedd3623d` | 续接映射；Batch1 未完成电芯剔除；严格 `<0.88` 与 `n+1` 标签规则；无容量平滑 |
| Nature Energy supplementary PDF | SHA-256 `5bd1e59d57daaf7778e42841c6aa0ffee6d286285d6968768ddb062fbe718a3c` | Supplementary Table 9 逐条列出论文纳入的 41 个 Batch1 电芯及 cycle life |
| 官方仓库 issue #9 的合作者答复 | Peter Attia, repository collaborator, 2019-07-19 | cycle 1 缺失原因；部分 `cycle_life` 加 1 是因为最后记录容量未低于 0.88 Ah |

`LoadData.m` 的公开历史中，Batch1 的标签规则自 2019-03-09 初始提交起未发生变化；公开的 BuildPkl notebooks 只复制 MAT 中的 `cycle_life`，未发现生成该字段的另一个平滑/窗口实现。Supplementary Information 中出现的 smoothing spline 用于拟合单循环内的 Q(V) 曲线，不用于 EOL/cycle-life 标签。

## 逐电芯对照结果

完整明细见 `docs/audits/v11_matr_cycle_life_per_cell.csv`。

| 审计语义类 | 电芯数 | stored 字段为 `n+1` | 排除缺失 cycle 1 后实测 `<0.88` | 末次 QDischarge (Ah) | Supplementary Table 9 |
|---|---:|---:|---:|---:|---|
| `official_continuation` | 5 | 5 | 0 | 0.97092122-1.04327860 | 5/5，使用官方 Batch1+Batch2 合并 cycle life |
| `official_cycle_life_eol` 候选 | 36 | 36 | 0 | 0.88005650-0.88336319 | 36/36，数值与 MAT `n+1` 完全一致 |
| `right_censored`（官方已知早停） | 5 | 5 | 0 | 0.91311944-0.96902454 | 0/5；`LoadData.m` 与 Batch1 notes 均明确排除 |
| `observed_eol_crossing` | 0 | - | - | - | 无 |

敏感性平滑仅用于审计，不属于官方定义：对排除缺失 cycle 1 后的容量序列计算 trailing 5-cycle 和 trailing 11-cycle median，46/46 个电芯的尾值仍高于 0.88 Ah；没有通过平滑得到 crossing。

## 为什么容量略高于 0.88 Ah 而官方 cycle life 仍成立

官方代码把这类情况定义为 `n+1`，而非宣称最后一个已记录循环已经低于阈值。论文合作者也明确说明，加 1 的原因正是最终记录容量仍未低于 0.88 Ah。因此该标签的语义是“官方策展的达到 EOL 的循环数约定”，不是“在 struct 中直接观测到的阈值穿越”。

对 36 个候选，权威性来自论文 Supplementary Table 9 和官方数据说明/加载代码的人工策展，而不是来自 `cycle_life=n+1` 这个数字本身。5 个早停电芯具有完全相同的数字模式，却被官方资料明确排除，证明 completion status 位于字段外的 provenance 中。

## 四类充分条件与互斥顺序

按下列顺序分类，命中后停止，保证互斥：

1. `observed_eol_crossing`：非续接电芯存在有效、真实测得的逐循环容量 `<0.88 Ah`；缺失 cycle 1 的 0 占位、异常值和未来信息不得使用。
2. `official_continuation`：电芯属于官方 Batch1->Batch2 映射 `[8,9,10,16,17] -> b1c0-b1c4`，且映射、连续结构、长度、官方 combined cycle life、源哈希全部通过门禁。该类不要求 Batch1 末端 crossing。
3. `official_cycle_life_eol`：非续接、无直接 crossing；必须逐电芯同时满足：出现在官方 Supplementary Table 9、表中 cycle life 与固定版本原始 MAT/官方规则一致、未落入 MATR notes 和 `LoadData.m` 的未完成/异常剔除集合、且不存在相反的官方停止原因。只满足 `cycle_life=n+1` 不充分。
4. `right_censored`：未满足前三类，或存在提前终止/来源冲突/无法追溯/未完成说明。文件末尾不能自动成为 EOL。

## 唯一根因假设

v10 的根因是把数值规则 `cycle_life = file_end + 1` 错当成 completion provenance。官方数据实际把“标签数值”和“试验是否完成”分散在不同载体中：数值位于 MAT/论文表，完成状态位于 Batch notes、Supplementary Table 9 的纳入集合和 `LoadData.m` 的人工剔除。忽略后者会把已知早停电芯和官方完成电芯错误地合并为同一 observed 类。

## 单一最小可证伪测试

在下一次单独批准后，只读获取官方 raw CSV/Arbin 末端协议元数据，并按 Supplementary Table 9 barcode 对 36 个候选做一次交叉验证：要求每个候选存在与 EOL 试验流程一致的末端停止/最终诊断记录，而 5 个已知早停电芯显示不同的非 EOL 终止原因。只要 36 个候选中任意一个出现与阈值无关的终止原因，或无法与官方 barcode/末端记录一致映射，就证伪“36 个均可升级为 `official_cycle_life_eol`”这一假设，并保持该电芯删失。

## 当前门禁决定

- v11 不变：36 个候选仍按现有 `right_censored` 保存，5 个 official continuation 是当前仅有的精确 observed 电芯。
- 不启动烟雾或正式训练，不放宽 1-cycle 标准，不修改 adapter/schema/manifest/data。
- 下一步必须由总工程师明确批准：是接受联合官方证据并以 TDD 增加 `official_cycle_life_eol`，还是先执行上述 raw CSV/Arbin 单一证伪测试。
