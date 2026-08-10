# 严格 RUL 公开来源目录发现与证据卡

日期：2026-08-05（Asia/Shanghai）  
状态：**发现阶段完成；保留 1 个待元数据核验候选，未下载、未接入、未授权训练。**

## 范围与硬门禁

本轮只浏览公开数据集记录和论文/补充页的可见元数据，最多筛选 3 个候选。没有调用登录或受限 API，没有下载任何文件，没有访问或重试 NASA、Oxford、MATR、BatteryLife 的已关闭路线，也没有修改代码、数据、adapter、schema、v11 或训练状态。

候选必须在具体数据集记录中同时显示：可直接访问、明确开放许可证、逐电芯数据、逐循环容量或可核验的 cycle 文件，以及明确的 EOL 合同现实可能。论文中的通用定义不能替代数据集许可证；文件终点不能自动成为 EOL。

## 录入前证据卡

### 1. Detection of the knee point in lithium-ion battery — 保留

- 官方记录：`https://data.mendeley.com/datasets/zn82y35zr8/4`
- 固定版本：Version 4，2025-01-28，DOI `10.17632/zn82y35zr8.4`
- 访问：公开网页可直接读取；页面提供公开文件入口，本阶段未点击下载
- 许可证：数据集记录明确显示 `CC BY 4.0`
- 数据规模与粒度：60 个 Samsung INR18650-30Q 电芯；每个电芯有 RPT CSV、Cycle CSV、SOH80 后 CSV 和处理特征；Cycle 文件名包含起止循环号
- EOL 合同：第一阶段从 SOH100 循环至 SOH80；第二阶段从 SOH80 循环至 SOH60；最高编号 RPT 被记录定义为完成循环后的 EOL RPT
- 任务边界：第一、第二寿命阶段协议不同，不得混合成单一监督任务；第一阶段含 9 种条件，第二阶段使用统一协议
- 尚待证伪：SOH 由每 50–100 cycles 的 RPT 测量；公开元数据尚未证明 SOH80/SOH60 crossing 可定位到单个物理 cycle，也未证明 60/60 电芯均无提前终止或缺失段
- 裁定：**保留为唯一的“只允许下一次元数据核验”候选；不构成下载、v12 或训练授权**

### 2. UNIBO Powertools Dataset — 排除

- 官方记录：`https://data.mendeley.com/datasets/n6xg5fzsbv/1`
- 固定版本：Version 1，2021-07-23，DOI `10.17632/n6xg5fzsbv.1`
- 访问：公开网页可直接读取；未下载
- 许可证：数据集记录明确显示 `CC BY 4.0`
- 数据规模与粒度：27 个电池；主循环连续记录，但容量测试在每 100 个主循环之后执行
- EOL 合同：页面只说明“重复直到 end of life”，未显示数值阈值、首个 crossing 规则或终止原因字段
- 裁定：**排除**。许可证通过，但 EOL 定义不明确且容量参考间隔为 100 cycles，不能支持 `<=1 cycle` 录入前门禁

### 3. Battery Degradation Dataset — Li Plating And SEI Growth — 排除

- 官方记录：`https://data.mendeley.com/datasets/m8w8sjk3vm/2`
- 固定版本：Version 2，2024-08-13，DOI `10.17632/m8w8sjk3vm.2`
- 访问：公开网页可直接读取；未下载
- 许可证：数据集记录明确显示 `CC BY 4.0`
- 数据规模与粒度：45 个 NMC/graphite coin cells，CCCV 充电、C/5 放电，公开记录说明包含 cycle data
- EOL 合同：数据集记录未显示逐电芯 EOL 阈值、终止规则、观察/删失状态或所有电芯均运行至 EOL的声明
- 裁定：**排除**。逐循环数据的存在不能替代 EOL provenance

## 发现阶段比较矩阵

| 数据集 | 页面直接可访问 | 明确许可证 | 电芯规模 | 逐循环现实可能 | 明确 EOL | 1-cycle 风险 | 结果 |
|---|---:|---:|---:|---:|---:|---|---|
| Knee point v4 | 是 | CC BY 4.0 | 60 | 是，逐电芯 Cycle CSV | SOH80 / SOH60 | RPT 间隔 50–100 cycles，精确 cycle 未证实 | **保留 1 个** |
| UNIBO v1 | 是 | CC BY 4.0 | 27 | 主循环有记录 | 否，仅写 EOL | 容量测试间隔 100 cycles | 排除 |
| Li plating v2 | 是 | CC BY 4.0 | 45 | 是，cycle data | 否 | 无终止/删失合同 | 排除 |

另有两个 Zenodo 发现项未进入三张候选卡：Panasonic 116-cell 页面首次访问返回 HTTP 429，按规则立即排除且不重试；KIT 228-cell 索引页的 Rights/License 字段为空，按许可门禁排除。二者均未下载、未调用 API。

## 唯一推荐与下一步

唯一推荐是对 `zn82y35zr8` **Version 4** 进行一次受限元数据核验，不下载数据文件。核验仅回答五个可证伪问题：

1. 固定版本记录的文件清单、文件 ID、大小、校验字段和 CC BY 4.0 是否能同时绑定 DOI `10.17632/zn82y35zr8.4`；
2. 是否存在 60 个电芯的完整唯一 ID 清单，且 Cycle/RPT/After-SOH80 三类文件可一一映射；
3. 第一阶段 SOH80 与第二阶段 SOH60 的 cycle index 是精确终止点，还是只能落在 50–100 cycle 的 RPT 区间；
4. 是否有提前终止、缺失轨迹、重复电芯或只由文件末尾推断 EOL 的对象；
5. 第一、第二阶段能否按协议独立定义任务，且不混合不同 EOL 基准。

任一答案缺失、元数据非公开、访问非 2xx、需要登录/API、或只得到区间 EOL，立即排除或降为 interval-censored，不重试、不下载。只有五项均通过后，才可另行申请下载与逐电芯 TDD；即使通过也不自动建立 v12，不授权烟雾或训练。

当前 v11 保持 `valid_for_training=false`、`training_authorized=false`。
