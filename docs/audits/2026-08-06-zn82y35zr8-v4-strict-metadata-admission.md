# Mendeley `zn82y35zr8` Version 4 严格元数据准入审计

审计日期：2026-08-06（Asia/Shanghai）  
对象：*Detection of the knee point in lithium-ion battery*, Version 4  
固定 DOI：`10.17632/zn82y35zr8.4`  
最终裁定：**NOT_ADMITTED（不准入）**。许可证门通过；文件实体映射、精确 cycle index、完整性/唯一性门均未由可访问的元数据证明。因此不得下载数据、不得接入 v12、不得训练，也不得将文件末尾或最高编号 RPT 当作观察到的 EOL。

## 1. 范围与不可越界项

本次是严格、只读的**元数据**审计，不是数据文件审计。仅核验固定版本页：

- `https://data.mendeley.com/datasets/zn82y35zr8/4`
- 未打开任何 file/download URL，未点击 `Download All`，未调用 OAuth/API 端点，未登录，未使用镜像，未下载 CSV 或压缩包。
- 未创建或修改 v12、adapter、schema、provenance、数据或训练结果；未运行训练或烟雾测试。

直接可复核的受控请求为对固定版本页的一次 `HEAD`：`2026-08-06 16:35:00 +0800`（响应 `HTTP/2 200`，未跟随重定向）。响应 `Link` 同时给出：

```text
<https://doi.org/10.17632/zn82y35zr8.4>; rel="cite-as"
<http://creativecommons.org/licenses/by/4.0>; rel="licence"
```

版本页的可读正文同时显示 Published `28 January 2025`、`Version 4`、该 DOI 和 `CC BY 4.0`。这些固定 URL 与页面字段是本审计的证据边界；没有据此推断未公开的文件内容。

## 2. 准入门与结果

| 准入问题 | 结果 | 可复核证据 | 严格解释 |
|---|---|---|---|
| Version 4 是否绑定 CC BY 4.0？ | **PASS** | 同一 Version 4 页面同时呈现 DOI `10.17632/zn82y35zr8.4` 与 `CC BY 4.0`；该页 HEAD 的 `Link` 还以 `rel="licence"` 绑定 CC BY 4.0 URL。 | 许可足以覆盖本固定记录；不从项目、作者或其他版本外推许可。 |
| 是否可证明恰有 60 个实际电芯？ | **METADATA CLAIM ONLY** | 描述称数据集含 `60` 个商业锂离子电芯；第二阶段称 all `60` cells 均继续测试。 | 这是出版方记录中的规模陈述，而不是逐电芯清单；不能据此断言 60/60 文件实体存在。 |
| Cycle、RPT、After-SOH80 是否可对每个电芯一一映射？ | **FAIL** | 页面只在“Steps to reproduce”中说明三类数据均按 cell 命名/文件夹组织：RPT 和 Cycle 是“folders named after each cell”，After-SOH80 是“CSV files named after each corresponding cell”。版本页的 Files 区没有公开可审计的文件名、cell ID、文件 ID、字节数或校验和清单。 | 没有 60 个规范化 cell ID 的集合，也没有三类文件的可枚举清单，无法计算 `Cycle ∩ RPT ∩ After-SOH80`，无法验证一对一、覆盖率或基数。 |
| 是否存在提前终止、缺失或重复电芯？ | **NOT VERIFIABLE / FAIL** | 元数据仅称每个 cell 有相应文件，并称最高编号 RPT 是 EOL 后测得的 RPT；未给出逐 cell 的阶段状态、预期文件数、文件哈希或唯一 ID 清单。 | 不能声称存在这些问题，也不能声称不存在。对准入而言，未能排除即失败；最高编号不能证明没有提前终止，文件名不能证明没有重复。 |
| SOH80 是否有精确 physical cycle index？ | **FAIL — interval-censored only** | 第一阶段每 `50–100` cycles（含 BOL/EOL）做 RPT 测 SOH；页面只说循环直到 SOH80。 | RPT 是离散检查。未公开“首次 SOH ≤80%”的逐 cycle 记录/字段；不能把 EOL RPT、RPT 序号、Cycle 文件终点或最后观测 cycle 当作 crossing cycle。只能形成相邻检查间的 `50–100` cycle 区间（确切宽度仍需文件证据）。 |
| SOH60 是否有精确 physical cycle index？ | **FAIL — interval-censored only** | 第二阶段每 `50` cycles 检查一次 `0.2C–0.2C` 容量，循环直到 SOH60。 | 定期检查并不定位阈值首次跨越的单个物理 cycle；没有逐 cycle crossing 字段时，最多是相邻检查间、宽度至多 50 cycles 的区间。 |
| 两个寿命阶段能否独立定义任务？ | **PASS（仅任务语义）** | 第一阶段：SOH100→SOH80，9 类运行条件；第二阶段：SOH80→SOH60，所有 60 电芯在 25°C 下采用统一、不同的循环协议。 | 可定义为两个**独立的区间删失**寿命任务，阈值和协议均不得混合。该语义结论不解除上列文件映射与精确标签门禁。 |

## 3. 映射与完整性判定的形式化说明

若要通过，公开的 Version 4 证据必须允许构造三个集合：

```text
C = {cell ID with Cycle files}
R = {cell ID with RPT files}
A = {cell ID with After-SOH80 files}
```

并证明 `|C| = |R| = |A| = |C ∩ R ∩ A| = 60`，每个集合内 cell ID 唯一，同时给出每个 cell 的阶段完成状态。当前元数据只给出命名规则和总体“60 cells”陈述，未给出这三个集合的成员，故上述等式完全不可计算。由此也无法识别或排除：

- 某电芯缺某一类文件；
- 第二阶段缺失或提前结束；
- 同一 cell 的重复命名/重复文件；
- 由文件最后 cycle、RPT 最大编号或 CSV 尾部伪造的 EOL 标签。

这不是“数据异常已发现”的主张，而是**元数据证据不足**的 fail-closed 判定。

## 4. 生命周期标签与任务边界

可保留的唯一元数据级解释如下：

1. 阶段一的事件为 SOH80，阶段二的事件为 SOH60；二者有不同的起点、阈值与运行协议，必须独立建模、独立切分、独立报告。
2. 阶段一的观测频率为每 50–100 cycles 一次 RPT；阶段二为每 50 cycles 一次容量检查。因此两阶段当前都不是 `<=1 cycle` 的观察事件，必须保持 interval-censored。
3. 最高编号 RPT 被描述为 EOL 后的测量，不能反向证明阈值恰在该 RPT 所对应的 cycle 跨越；Cycle CSV 的命名区间亦不能替代原始阈值 crossing 记录。

故“可以独立定义任务”只表示研究问题在协议上可分，不表示其具备逐 cycle 监督、完整 60-cell 队列或训练准入资格。

## 5. 最终准入结论

| 必要条件 | 状态 |
|---|---|
| 固定版本、DOI 与明确许可 | 通过 |
| 60 个 cell 的文件级唯一映射 | 失败 |
| 逐 cell 完整性、无提前终止/缺失/重复 | 未证实，按失败处理 |
| SOH80 精确 cycle index | 失败（区间删失） |
| SOH60 精确 cycle index | 失败（区间删失） |
| 两阶段可独立定义 | 通过，但仅限区间删失语义 |

任一必要条件失败即不准入。本数据集在文件实体与精确 EOL 两个硬门失败，故结论为 **NOT_ADMITTED**。本结论不授权下载、接入 v12、provenance 提升、训练、烟雾运行或以其生成 `<=1-cycle` RUL 标签。

若未来用户提供随包的**官方 Version 4**本地证据，重新审计至少应包含：版本绑定许可快照、完整文件 manifest（cell ID、路径、大小、哈希）、三类文件的 60-cell 双向映射、逐 cell 阶段完成/删失原因，以及能够定位 SOH80/SOH60 首次物理 crossing cycle 的原始记录。若原始试验只能按 RPT 频率观察阈值，则即使文件齐全也仅可考虑两项独立 interval-censored 任务，不能改写为精确 cycle 终点。

## 6. 官方复核入口

- [Mendeley Data Version 4 记录](https://data.mendeley.com/datasets/zn82y35zr8/4)
- [固定 DOI](https://doi.org/10.17632/zn82y35zr8.4)
- [CC BY 4.0 许可证](https://creativecommons.org/licenses/by/4.0/)

