# 严格 RUL 本地合规候选矩阵与下一步方案

日期：2026-08-05（Asia/Shanghai）  
结论：**当前合规新候选为 0；v11 继续冻结，严格 RUL 仍为 NOT READY。**

## 本轮边界

本轮只读取本地已有实体、许可证文件、manifest 和既有审计。没有访问 NASA、Oxford、MATR 或 BatteryLife 的已关闭网络路线；没有发起其他网络请求、下载、训练、烟雾或真实拟合；没有修改代码、数据、adapter、schema、v11、标签或 provenance。

精确 RUL 候选必须同时通过：明确并绑定具体版本的开放许可证、本地或官方直接 2xx 的可复核实体、唯一电芯映射、逐循环物理 EOL/删失合同，以及足够支持严格电芯留出的规模。配置中的 `status: approved` 或描述性许可文本不等于准入。

## 当前候选矩阵

| 本地来源 | 许可证与实体 | RUL/EOL 证据 | 当前允许用途 | v12 精确 RUL 候选 |
|---|---|---|---|---|
| MATR Batch1/2 | 已有复合官方 CC BY 4 证据、固定本地实体及哈希 | 仅 `b1c0`–`b1c4` 五个 `official_continuation` 可作精确 observed；36 候选和 5 早停仍为 `right_censored` | 五电芯证据保留；删失分析 | **否：规模不足；关闭路线不重试** |
| Oxford degradation | 本地 manifest 明确 ODbL 1.0，实体有 SHA-256 | 8 电芯、519 观测；中位网格 100 cycles，EOL 区间宽 100–200 cycles | interval-censored / 100-cycle-grid 独立诊断 | **否：不能支持 `<=1 cycle`** |
| Stanford LFP SOC 2025 | 数据包内含 MIT LICENSE；README 明确数据任务与论文 | 8 电芯的容量、GITT、OCV、SOC 训练/验证工况；没有寿命终止协议或逐循环 EOL | SOC/工况研究 | **否：任务不匹配** |
| NASA PCoE classic/randomized | 具体数据集许可证未明确；classic 本地包无绑定许可快照 | 既有 crossing 预审不能越过许可门禁 | 只读不准入结论 | **排除；禁止重试/下载** |
| BatteryLife / Zenodo 21149533 | 本地 `batterylife_v12_life_labels` 目录为 0 文件；“Open Zenodo dataset”仅是配置描述，官方元数据路线已关闭 | 无本地实体、版本许可证或可复核 EOL 文件 | 无 | **排除；禁止重试/下载** |
| CALCE A123 dynamic | 本地实体有哈希，但 manifest 的“Research/publication use...”不是明确许可证 | 动态 SOC 工况，不提供可复核寿命终止合同 | 当前仅保留来源事实 | **排除：许可和任务均失败** |
| Sandia cell cycle archive | 本地实体有哈希，但“Public research repository...”是描述性文本，不是明确许可证 | 缺少权威的唯一电芯—终止原因—EOL cycle 映射 | 当前仅保留来源事实 | **排除：许可和终止证据失败** |
| `nasa_randomized_recommissioned` 本地目录 | 0 文件，无许可证实体 | 无 | 无 | **排除** |

## 一页下一步方案

### 推荐裁定

维持冻结，不从现有目录强行构造 v12。当前没有一项“再解析一次本地文件”能够补齐缺失的许可证、逐循环 EOL 或样本规模；继续在已关闭来源上尝试只会重复失败，不能提高证据强度。

### 允许恢复的单一入口

仅在总工程师明确指定一个**新的**官方来源，或用户提供一个本地官方数据包时，启动一次来源级只读准入。输入必须同时包含：

1. 随包 LICENSE/官方许可页快照，能够绑定数据版本；
2. 原始文件清单、字节数和 SHA-256；
3. 电芯 ID 与文件/轨迹的一一映射；
4. 官方 EOL 定义、终止原因、逐循环 cycle index，或可证明的相邻上下界；
5. 明确的右删失规则，禁止以 file-end 或 `cycle_life` 数字自动补 EOL；
6. 足够进行严格未见电芯训练/验证/测试划分的 observed 电芯规模。

### 后续门禁顺序

1. **许可证与访问门禁（只读）**：非明确许可、非官方、非直接 2xx 或实体指纹缺失，立即排除；不绕过、不换镜像。
2. **逐电芯可证伪审计（只读）**：输出 cell→file→protocol→EOL/censoring 矩阵；任一映射不唯一，该电芯保持删失。
3. **TDD 接入申请**：只有前两项全通过，才提交 adapter/schema 与独立 v12 的最小变更计划；先 RED 后 GREEN。
4. **数据门禁**：v12 独立构建，不覆盖 v11；通过许可证、哈希、EOL、因果、分组留出和删失一致性门禁。
5. **训练仍需另批**：即使 v12 数据门禁通过，也不自动授权烟雾或正式训练，不改变 `<=1 cycle` 标准。

### 完成定义

本阶段已完成的交付仅是候选矩阵与恢复方案。当前正确终态是“0 个新候选、保持冻结”，不是训练可用或模型达标。

关联证据：`docs/audits/2026-08-04-open-rul-source-catalog-audit.md`、`docs/audits/v11_rul_final_data_admission.md`、`docs/audits/v10_oxford_rul_observability.json`、`docs/audits/2026-08-04-nasa-classic-rul-admission-final.md`。
