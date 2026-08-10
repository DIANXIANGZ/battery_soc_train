# 严格 RUL 物理 EOL 数据准入决策（只读阶段）

日期：2026-08-04　　状态：**NOT READY；v11 保持冻结；不授权烟雾或正式训练。**

## 决策摘要

当前没有来源足以立即解除 `RUL MAE <= 1 cycle` 的数据阻塞。MATR 仍只有 5 个 `official_continuation` 精确电芯；Oxford 只能提供 100–200 cycle 宽的区间标签；Sandia 缺少可复核终止语义。唯一值得进入下一轮 TDD 的候选是本地已下载的 NASA PCoE 经典老化档案，但它仍须先解决许可证未指定、逐电芯协议一致性和异常容量记录三项门禁。建议总工程师仅批准 **NASA 经典老化档案的 v12 前置 TDD/准入审计**，暂不批准 v12 重建或任何训练。

## 精确 RUL 最小证据合同

| 合同层 | 精确点标签的充分条件 | 失败后的处理 |
|---|---|---|
| 来源 | 官方落地页/仓库、不可变版本或实体指纹、下载时间、字节数、SHA-256、明确许可 | 来源不可复核或许可缺失：冻结，不进入 v12 |
| 电芯身份 | 官方 cell ID 与原始文件/对象一一映射；续接、重复、拆分轨迹均有权威映射 | 缺失、重复或猜测映射：`right_censored` |
| EOL 语义 | 官方物理阈值/失效条件明确；且有相邻物理循环 crossing，或有权威续接轨迹精确定位终止 cycle | file-end、`cycle_life`、表格收录或字段缺失均不构成 EOL |
| 分辨率 | cycle 索引代表同一协议下的一次物理循环；crossing 区间宽度 `<=1 cycle` | 宽度 `>1`：仅 `interval_censored` 诊断 |
| 因果性 | 标签可使用完整终止轨迹；模型输入在预测时刻仅含前缀，未来扰动不得改变前缀特征/划分 | 任一未来信息进入特征、归一化或选择：整版失效 |

## 来源/电芯/终止语义/分辨率/可用性矩阵

| 来源与电芯 | 终止语义与分辨率 | 当前可用性 |
|---|---|---|
| MATR `b1c0–b1c4`（5 cells；9,381 rows） | 官方 Batch1→Batch2 续接；cycle 级标签 | 标签语义可作点监督，但规模不足且 v11 未授权；只读审计 |
| MATR 36 候选：`b1c5,b1c6,b1c7,b1c9,b1c11,b1c14–b1c21,b1c23–b1c45`（不含下列早停） | 官方 detail schema 无 termination/EOL 字段；本轮 Metadata 文件元数据 HTTP 200，但 Metadata CSV 为 HTTP 301，未跟随 | 全部 `right_censored`；不得提升 provenance |
| MATR 早停 `b1c8,b1c10,b1c12,b1c13,b1c22` | 非 EOL 终止已知 | `right_censored` |
| Oxford `Cell1–Cell8`（519 observations） | 中位 100-cycle 网格；EOL bracket 宽 100 或 200 cycles；官方对象直读本轮 HTTP 403 后停止 | 仅 interval/grid 诊断；禁止 1-cycle 点验收 |
| NASA 经典老化档案：`B0005,B0006,B0018,B0033,B0034,B0036,B0038–B0040,B0042–B0044,B0046–B0048`（15 cells） | 官方 README 声明 1.4/1.6 Ah 终止组；原始 `.mat` 存在相邻 above→below 阈值转折，逐放电循环分辨率 | **仅候选**；须验证相邻循环协议等价、异常容量排除规则和许可后才可请求准入 |
| NASA 同类但无可用相邻 crossing：`B0007,B0041,B0045,B0053–B0056`（7 cells） | `B0007` 未降至 1.4 Ah；其余从首条容量即低于阈值，无法建立上/下界相邻 crossing | `right_censored`，不得以 file-end 补标签 |
| NASA 未声明 EOL/软件崩溃组：其余 12 个唯一电芯 | README 未给出完成 EOL，或明确因控制软件崩溃结束 | `right_censored` |
| NASA Randomized `RW9–RW12` | 仅间隔插入的 reference discharge；现有 `cycle_id` 是参考测量序号，不是逐物理循环；代码仍为 70% 而现有 manifest/audit 为 80% | 当前标签合同不一致且分辨率不足；禁止精确 RUL |
| Sandia 本地 archive（200 workbooks / 111 basename conditions） | 官方页称 public raw data，但 README DOCX 读取返回不支持；本地包无终止原因文件，物理 cell/Reg/Mod 映射未裁定 | 全部按删失候选；不能独立承载 1-cycle 验收 |
| CALCE 动态数据（v11 四源） | 每源仅 2 cells / 2 cycles，属于动态工况而非生命周期终止轨迹 | 不可用于 RUL |

注：NASA 官方 archive 为 `Battery_Data_Set.zip`，SHA-256 `82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e`，34 个唯一电芯；NASA 官方 Open Data 页面明确 2.0→1.4 Ah EOL，但页面显示 `License not specified`。NASA 各实验组 README 还存在 1.6 Ah、软件崩溃和未声明终止等不同语义，因此不得联合成单一标签规则。

## 拟提升 provenance 的最小可证伪测试（先 RED）

1. `observed_eol_crossing/NASA`：逐电芯断言官方组阈值、相邻 cycle `C[n-1] > threshold >= C[n]`、两循环的温度/电流/截止电压/容量计算协议一致，且 cycle 映射无缺失或重复；任一反例即该电芯删失。
2. 异常鲁棒性：注入首循环低容量、零容量或协议切换记录，测试必须拒绝把异常点当 EOL；不得凭平滑或“最后一次 crossing”自动修复。
3. 来源能力：缺 license/version/hash/cell mapping 任一字段时 fail-closed；NASA 许可未解决前 capability 必须为 false。
4. Oxford：任何 bracket 宽度 `>1` 必须进入 `interval_censored`，且构建精确点训练表应失败。
5. MATR：36+5 的 `rul_observed` 必须恒为 0；Metadata 缺少终止字段或 HTTP 301 不得改变 provenance。
6. 因果回归：改变 crossing 后的未来尾段不得改变此前任何特征、归一化、分组或模型选择输入。

## 推荐方案、风险与工时

推荐只推进 NASA 经典老化档案，且作为独立的 **NASA-1.4Ah / NASA-1.6Ah 分任务**，不与 MATR/Oxford 混合。第一阶段只做来源许可裁定和 15 个候选的逐电芯协议 TDD；若少于足以形成可辩护的 train/validation/test 电芯规模，则停止，不建 v12。Oxford 保持区间诊断；MATR 和 Sandia 保持删失。

- 来源许可与版本/哈希能力门禁：2–3 小时；若仍为 `License not specified`，立即停止并请求用户/法务裁定。
- 15 个 NASA 候选的逐电芯协议审计、RED/GREEN 门禁：6–8 小时。
- 仅在前两项通过后，独立 v12 adapter/manifest、全量数据与因果门禁（不训练）：6–8 小时。
- 总计：约 14–19 工时；不包含训练、调参或 `<=1-cycle` 模型验收。

## 证据与受控网络结果

- 既有：`docs/audits/v11_rul_final_data_admission.md`、`v11_matr_b1c31_detail_curl_final_audit.json`、`v11_matr_cycle_life_per_cell.csv`、`v10_oxford_rul_observability.json`。
- MATR 本轮：2026-08-04 14:02:55Z–14:03:01Z，`GET https://data.matr.io/1/api/v1/file/5c86c0b5fa2ede00015ddf6d` → HTTP 200 JSON，291 bytes，ETag `905e35f7d327ab3bc6ebe8ffd6e45360`，Last-Modified `2019-03-25T15:20:14Z`，SHA-256 `c25a5b5bd85dfc5b4ea92befaecfcc054782f44aea541c1d710345a7a293f12f`。2026-08-04 14:03:16Z–14:03:19Z，同一 ID 的 `/download` → HTTP 301，0 bytes，Location `/assetstore/d3/73/d37375a8e16549f8b92f9b348bbb0169`；未跟随，来源路线关闭。
- Oxford 本轮：官方 `https://ora.ox.ac.uk/objects/uuid:03ba4b01-cfed-46d3-9b1a-7d4a7bdf6fac` 直读 HTTP 403，按门禁停止且未重试。
- Sandia 本轮：官方 `https://www.sandia.gov/app/uploads/sites/163/2022/02/README_Cycle_Data-1.docx` 返回 unsupported content-type，按门禁停止；未下载替代文件。
- NASA：官方 PCoE repository 与 Open Data 页面均确认 Battery Data Set/物理 EOL 说明；本地官方 archive 哈希与 manifest 一致。许可证仍未指定。

**待总工程师裁定：是否批准“仅 NASA 经典老化档案的来源许可 + 15 电芯逐协议 TDD”，并继续保持 v11、训练、烟雾与阈值全部冻结。**
