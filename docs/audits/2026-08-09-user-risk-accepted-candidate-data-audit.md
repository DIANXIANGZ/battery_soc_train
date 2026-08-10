# 用户风险接受的候选数据审计

日期：2026-08-09（Asia/Shanghai）  
状态：**一次性受控只读候选数据审计；不是技术来源准入，不授权数据版本、实现、测试、烟雾或训练。**  
来源标记：`RISK_ACCEPTED_SOURCE_BINDING`（仅记录用户接受来源风险；不得解释为官方来源已获技术准入）。

## 1. 范围与边界

本次只读取以下既有对象：

- Archive：`/Users/wanghaoming/Public/SOC电池数据中心/Battery raw data.zip`
- 既有解压目录：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/Battery raw data`

未联网、未下载、未重试来源、未解压或复制数据；未修改 ZIP、CSV、XLSX、代码或配置；未创建 manifest、canonical table、数据版本、运行目录或模型产物；未运行测试、烟雾或训练。审计 CSV 只含路径、ID、计数、状态和证据定位，不含原始测量值。

## 2. 门禁结论

| 门禁 | 裁定 | 主要计数 | 影响 | 最小下一步 |
|---|---|---:|---|---|
| ZIP 与既有解压结构绑定 | **PASS（结构绑定）**；来源仍为 `RISK_ACCEPTED_SOURCE_BINDING` | ZIP 非目录成员 1,712；正常数据树 792；`__MACOSX` 920；792/792 路径、size、CRC 全匹配 | 证明现有解压树与现有 ZIP 实体一致；不证明 ZIP 的官方来源身份 | 若要解除来源门，仍需总工程师认可的新来源证据；不得把本结构 PASS 写成官方准入 |
| 60-cell C/R/A 文件映射 | **PASS（文件身份层）** | C=60 cells/304 files；R=60/360；A=60/60；C∩R∩A=60；另有 0.033C RPT 60/60 | 可以按名称中的前导整数 ID 和完整条件 token 唯一定位物理 cell；不依赖目录顺序 | 后续若获授权，映射应原样进入独立审计 manifest，并继续保留文件级 provenance |
| 两阶段 EOL 端点与删失 | **NOT_VERIFIABLE** | 60 cells × 2 stages = 120 个 `invalid_protocol`；observed/right/left 均为 0 | 不能生成任何有限区间、right-censored 或精确 RUL 标签 | 提供权威阈值参考、容量步骤定义及 RPT/第二阶段检查到物理 cycle 的逐 cell 对齐证据，再重新审计 |
| 阶段隔离与未来信息 | **NOT_VERIFIABLE（总体）** | 静态文件分区 1 项 PASS；cell token 复用 1 项 PASS；协议/可用前缀 1 项 NOT_VERIFIABLE；实现路径 1 项 `NOT_VERIFIABLE (not implemented)` | 只能证明文件角色分区，不能声称无未来泄漏 | 获新授权后先定义 prediction-time 可观测前缀，再以未来尾段扰动和 cell-level LOCO 测试验证 |

因此，非来源门仍存在 `NOT_VERIFIABLE`，总体状态保持 **`NOT_ADMITTED` / 不可训练**。

## 3. ZIP 与解压结构绑定

### 3.1 Archive 指纹

- Archive filename：`Battery raw data.zip`
- 绝对路径：`/Users/wanghaoming/Public/SOC电池数据中心/Battery raw data.zip`
- Bytes：`1,465,986,814`
- SHA-256：`6dbce36660bd320efed23fc573ec145d1ccaf37c00abcd42abd2587d545e4f3b`
- 既有解压根：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/Battery raw data`

ZIP 中共有 1,712 个非目录 member，其中 920 个位于 `__MACOSX/`，仅为 macOS 元数据，明确排除；剩余 792 个为数据树成员。ZIP member 名称中的字节序列在 Python ZIP 解码后把度数符号显示为 `┬░`，而既有解压路径显示为 `°`。本审计只应用单一、可逆且无碰撞的名称比较规则 `┬░ -> °`；规范化后得到 792 个唯一相对路径。

792/792 个数据树 member 均找到对应的既有解压文件，且 uncompressed size 与对解压文件重算的 CRC32 全部一致：missing=0、extra=0、size mismatch=0、CRC mismatch=0。逐 member 证据见 `2026-08-09-user-risk-accepted-candidate-archive-binding.csv`。

该结果只支持“现有 ZIP 与现有解压树绑定一致”。由于来源风险由用户接受，本报告固定写为 `RISK_ACCEPTED_SOURCE_BINDING`，不升级为官方技术准入。

## 4. 60-cell C/R/A 映射

### 4.1 规范化规则

每个角色均从路径实体本身取 token，不按目录顺序配对：

1. `Cycle Data/<cell token>/...`：取目录名前导整数 1–60 和其余完整条件描述；
2. `RPT Data/<cell token>/...`：同上；
3. `After SOH80 Data/<cell token>.csv`：取文件名前导整数，并只移除固定角色前缀 `CYCLE_after_SOH80_`；
4. `0.033C RPT Data/<cell token>.csv`：作为单独辅助 RPT 角色记录，不混入 primary R 文件计数。

只对 Unicode、空白和前导编号后的可选句点作规范化。诸如 cell 27/40 无编号后空格、Cycle cell 56 缺编号后句点等格式差异仍可由前导整数和完整条件 token 唯一解析；60 个 cell 的四角色条件描述全部一致，未出现无法解析名称或 token collision。

### 4.2 计数与冲突

- Cycle：60/60 cells，304 files，每 cell 3–8 files；
- RPT：60/60 cells，360 files，每 cell 4–8 files；
- After-SOH80：60/60 cells，60 files，每 cell 1 file；
- 0.033C RPT：60/60 cells，60 files，每 cell 1 file；
- `|C|=|R|=|A|=|C∩R∩A|=60`；
- missing roles=0、duplicate top-level cell token=0、token collision=0、同一相对路径跨 cell/role/stage reuse=0；
- primary C/R/A 内 CRC32+size 重复实体组=0。

Cycle 文件名的声明区间中仅发现一处边界重合：cell 21 的 `CYC 101-115` 与 `CYC 115-130`。对这两个实际 CSV 的 `TotCycle` 字段只读核验分别为 103–118 与 119–134，实际字段不重叠；但这同时说明“文件名 cycle 范围”与 tester `TotCycle` 并非同一编号语义，因此不能用文件名建立 EOL。该问题不破坏 file→cell 映射，却直接阻断端点语义外推。

逐 cell 路径和计数见 `2026-08-09-user-risk-accepted-candidate-cell-mapping.csv`。

## 5. 字段、EOL 端点与删失

### 5.1 实际字段

只读表头审计结果：

- 304 个 Cycle CSV：1 种表头；
- 360 个 RPT CSV：2 种表头（359 个带尾部 `Unnamed: 20`，1 个不带）；
- 60 个 After-SOH80 CSV：2 种表头（48/12，差异为额外索引列）；
- 60 个 0.033C RPT CSV：1 种表头。

这些文件均暴露 tester 字段 `CurCycle`、`TotCycle`，以及 `Capacity(Ah)`、`Capa. Sum(Ah)`、`Char. Cap.(Ah)`、`Dischar. Cap.(Ah)`。字段存在不等于其可作为 SOH80/SOH60 阈值标签：

- Stage 1：RPT 文件名只有 0、1、2…的检查序号，CSV 内的 `TotCycle` 是 RPT 程序内部循环（代表性文件为 1–31），没有把该 RPT 明确绑定到物理老化 cycle 的字段；Cycle chunk 的 `TotCycle` 又会包含与文件名范围不同的偏移。
- Stage 2：After-SOH80 文件含连续 tester `TotCycle` 和容量字段，但没有权威 SOH60 capacity reference、标准化检查步骤或“首次低于阈值”字段。`2nd_lifetime.xlsx` 只读可见 60 个 cell number 和列标题，除 cell number 外未发现可用数据值。
- 处理后文件 `0.2C & 1C_Capacity.xlsx` 提供 RPT-indexed 容量，但没有物理 cycle 对齐字段，且属于 processed artifact，不能替代原始协议 provenance。

### 5.2 严格裁定

由于阈值参考、容量步骤含义或物理 cycle 对齐至少一项不明确，全部 60 cells 的两个阶段均裁定 `NOT_VERIFIABLE`，并写为 `censoring_class=invalid_protocol`。未把任何行转换为 `interval_observed`、`right_censored` 或 `left_censored`；未使用 file-end、RPT 最大编号、目录末项、平滑或估计生成 crossing。

逐 cell/stage 的字段和证据定位见 `2026-08-09-user-risk-accepted-candidate-endpoint-censoring.csv`。

## 6. 阶段隔离与未来信息

静态文件层面：Stage 1 使用 `Cycle Data`/`RPT Data`/`0.033C RPT Data`，Stage 2 使用 `After SOH80 Data`，没有相同相对路径或相同 CRC32+size 实体跨 primary role 复用；60 个 token 在两阶段重复代表同一物理 cell 身份，未来切分必须按 `physical_cell_id` 分组，不能把同一 cell 的两个阶段分到训练/测试两侧。

但本次没有获准实现或检查特征、归一化、split、模型选择、早停或训练路径；同时端点协议与 prediction-time 可观测前缀尚未闭合。因此：

- 文件角色分区：PASS；
- 物理 cell token 一致性：PASS；
- 协议边界与可用前缀：NOT_VERIFIABLE；
- 特征/归一化/切分/模型选择/训练无未来泄漏：`NOT_VERIFIABLE (not implemented)`。

不得把上述静态文件 PASS 写成“无泄漏 PASS”。控制项见 `2026-08-09-user-risk-accepted-candidate-stage-isolation-leakage.csv`。

## 7. 门禁总裁定

1. 来源风险：用户已接受，固定标记 `RISK_ACCEPTED_SOURCE_BINDING`；不等于官方来源技术准入。
2. ZIP/解压结构：PASS。
3. C/R/A 文件身份映射：PASS。
4. 端点/删失：NOT_VERIFIABLE，120/120 cell-stage 均为 `invalid_protocol`。
5. 阶段隔离/泄漏：静态文件分区 PASS，但协议前缀和全部实现路径 NOT_VERIFIABLE。

任一非来源门的 FAIL/NOT_VERIFIABLE 均不得因用户接受来源风险而绕过。总体仍为 **`NOT_ADMITTED`**；数据版本、实现、测试、烟雾和训练继续未获授权，不得称该候选数据“可训练”。

## 8. 只读命令摘要与完整性声明

使用的只读操作类型：

- `stat`、`shasum -a 256`：记录 archive path/bytes/SHA；
- `unzip -Z -1`、Python `zipfile`：读取 member name/CRC/uncompressed size，不解压；
- `find`：枚举既有解压路径和角色目录；
- Python `zlib.crc32`：对既有解压文件只读重算 CRC，与 ZIP member 对照；
- Python `csv`：读取 CSV 表头及少量必要的 `TotCycle` 定位字段，不复制测量值；
- bundled Python `openpyxl` 的 `read_only=True`：读取既有 XLSX 的 sheet/header/非空字段状态，不保存 workbook；
- `wc`、`shasum`、CSV 状态计数脚本：核对审计产物行数、状态和 SHA。

没有运行 pytest、compile、烟雾或训练命令。没有修改数据、代码或配置。

## 9. 审计产物 SHA-256

| 产物 | SHA-256 |
|---|---|
| `2026-08-09-user-risk-accepted-candidate-archive-binding.csv` | `91146f884dbac37c341506bdd68d82925379b8832c825e39984409dd0b8911c3` |
| `2026-08-09-user-risk-accepted-candidate-cell-mapping.csv` | `e1610713750265caf7c4e0f69c973910b6b5335228c230ce1f0cc3443b453e99` |
| `2026-08-09-user-risk-accepted-candidate-endpoint-censoring.csv` | `be864518c679a307c59749ef3ce4730b804b78b66707e9212e386fa202052a0a` |
| `2026-08-09-user-risk-accepted-candidate-stage-isolation-leakage.csv` | `06fabcb932adcd8377ecb4235cfa98ce8edee874104bd89eb8d9a678d1178a9d` |

