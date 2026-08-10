# NASA 经典老化档案严格 RUL 准入裁定

日期：2026-08-04　　裁定：**NOT_ADMITTED；来源排除；严格 RUL 仍 NOT READY。**

## 结论

NASA PCoE 经典老化档案不得进入 v12、不得提升 provenance、不得下载、不得训练。NASA Open Data 对该数据集的许可字段为 `License not specified`；NASA 的通用 CC0/政府公开数据说明没有可复核证据明确绑定到该 PCoE 实验档案，不能自行外推。唯一受控官方快照请求又在 TLS 层失败（curl exit 35、HTTP 000），没有响应实体可做版本指纹。按照“许可不确定或网络异常立即停止”的门禁，本来源已停止，不重试、不换客户端、不跟随重定向、不用镜像。

## 官方来源与快照

| 项目 | 结果 |
|---|---|
| 官方目录 | `https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/` |
| 数据集页 | `https://data.nasa.gov/dataset/li-ion-battery-aging-datasets`；许可字段 `License not specified` |
| 受控请求 | 2026-08-04 14:13:46Z–14:13:55Z；curl 8.7.1；exit 35；HTTP 000；无响应实体/ETag/Last-Modified/SHA-256 |
| 本地官方 archive | 209,708,670 bytes；SHA-256 `82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e`；未捆绑明确许可快照 |
| 许可适用性 | Science Data Portal/Earthdata 的 CC0 文本仅明确覆盖相应 NASA-led mission/数据系统；不足以覆盖本数据集的未指定许可 |

## 15 个 crossing 候选的处理

15 个候选全部为 `NOT_EVALUATED_LICENSE_BLOCKED`，当前继续按 `right_censored` 处理。此前只读预审发现的相邻容量转折仅用于说明潜在审计对象，不构成协议通过或 EOL provenance。由于来源许可门禁先失败，本阶段没有创建协议验证器、没有写 RED 测试、没有运行 `.mat` 协议 TDD，也没有以平滑、最后一次 crossing 或 file-end 补标签。逐电芯状态见 `docs/audits/2026-08-04-nasa-classic-rul-cell-matrix.csv`。

## 永久来源规则

后续只允许同时满足以下条件的数据集进入审计候选：

1. 许可证明确、开放合法，并能绑定到具体数据版本；
2. 官方端点可直接正常访问；
3. 不需要登录、绕过 403/防火墙/反爬/访问控制或跟随受限重定向；
4. 不使用镜像替代受限官方来源；
5. 原始文件、许可、版本、字节数和 SHA-256 均可复核。

任何条件失败，只保留 NOT_ADMITTED 只读结论，不下载、不训练、不纳入 v12。

## 状态与下一步

- `nasa_classic_admitted=false`
- `protocol_tdd_authorized=false`
- `v12_authorized=false`
- `training_authorized=false`
- v11、MATR、Oxford 和既有 provenance 全部保持原冻结状态。
- 下一步仅做本地已有或官方端点可直接 2xx 访问、且许可证明确的开放电池数据集目录审计；在找到同时满足许可、逐循环物理 EOL 和足够电芯规模的来源前，不申请 v12。

证据：`docs/audits/2026-08-04-nasa-classic-license-snapshot.json`、`docs/audits/2026-08-04-nasa-classic-rul-cell-matrix.csv`。

