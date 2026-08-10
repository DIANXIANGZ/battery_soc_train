# SOE 本地候选来源门只读审计

日期：2026-08-09（Asia/Shanghai）  
范围：仅本地元数据、archive 实体与既有审计证据；不读取样本行。  
**唯一结论：FAIL（冻结来源资产精确命中；停止于来源门）。**

## 已核验事实

- 候选 archive：`/Users/wanghaoming/Public/SOC电池数据中心/Battery raw data.zip`；`1,465,986,814` bytes；SHA-256 `6dbce36660bd320efed23fc573ec145d1ccaf37c00abcd42abd2587d545e4f3b`（本次仅 `stat`、`shasum`）。闭合 denylist 的资产 `interval_rul_archive` canonical root 与此路径精确相等，故按“root/后代命中即 FAIL”规则拒绝。
- 既有受控审计报告 [2026-08-09-user-risk-accepted-candidate-data-audit.md](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-user-risk-accepted-candidate-data-audit.md)，SHA-256 `dc5e5c1624007369f11372ece716075488778debc6ce0ba899ff132ad7a1310e`，证明 ZIP/既有解压结构绑定；该绑定的固定来源状态是 `RISK_ACCEPTED_SOURCE_BINDING`，不构成官方技术来源准入。
- 文件清单/实体绑定证据：[archive-binding.csv](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-user-risk-accepted-candidate-archive-binding.csv)，SHA-256 `91146f884dbac37c341506bdd68d82925379b8832c825e39984409dd0b8911c3`；既有审计记录 792/792 数据树成员匹配。物理 cell/角色清单：[cell-mapping.csv](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-user-risk-accepted-candidate-cell-mapping.csv)，SHA-256 `e1610713750265caf7c4e0f69c973910b6b5335228c230ce1f0cc3443b453e99`。
- 表头级既有审计仅记录 Cycle/RPT/After-SOH80/0.033C-RPT 四类文件的表头类数和 tester 字段；没有 SOE 目标定义、SOE 标签字段绑定或 SOE 专属来源 manifest。端点/表头审计证据：[endpoint-censoring.csv](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-user-risk-accepted-candidate-endpoint-censoring.csv)，SHA-256 `be864518c679a307c59749ef3ce4730b804b78b66707e9212e386fa202052a0a`。
- 冻结资产拒绝：闭合控制台账 [2026-08-09-frozen-rul-asset-denylist.json](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json)，SHA-256 `44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`，资产 ID `interval_rul_archive`、canonical root `/Users/wanghaoming/Public/SOC电池数据中心/Battery raw data.zip`；该精确命中使 `source_binding` 与 `frozen_denylist` 均为 FAIL。分工台账仍为 [work-allocation-ledger.md](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-non-rul-source-admission-work-allocation-ledger.md)，SHA-256 `199cb41fb273d35830bb5725b9babd8d492ab09a1d78649bbad81b7ae1dd85e5`。未访问冻结资产内容。

## 缺口与精确停止点

精确冻结命中已使 SOE 来源门 FAIL；SOE 专属 source/version/license manifest、标签/单位/参考基准 header-level 绑定和零命中证据的缺口仅记录，不能弱化或替代冻结拒绝。

因此不对许可证/版本、SOE schema/header 或冻结拒绝以外的任何训练适用性作推断；未读取样本行，未运行实现、测试、烟雾或训练，未下载或修改任何对象。

**最小下一步：** 总工程师明确解除或替换该冻结候选来源后，才可凭 SOE 专属、本地可复核的来源/版本/许可证 manifest 与已脱敏 header inventory 重新执行来源门。
