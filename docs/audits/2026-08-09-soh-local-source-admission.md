# SOH 既有本地来源门只读审计

日期：2026-08-09　目标：`SOH`　唯一结论：**FAIL**  
精确停止点：`SOURCE_ENTITY_ABSENT`。来源 PASS 也不授权后续动作；本结论更不授权实现、TDD、数据版本、烟雾或训练。

## 核验结果

| 门 | 结果 | 证据与解释 |
|---|---|---|
| 许可证 | `NOT_VERIFIABLE` | [`LICENSE`](/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/02_Stanford_LFP_SOC_2025/raw/LICENSE)，SHA-256 `c41fe9f8ebd7557555b998d212861b322754fffb581a06185ee64bdff259ff58`，1,065 bytes。MIT 文本明确指向 software/associated documentation；本地没有证据证明它绑定数据实体。 |
| 来源/版本记录 | `DESCRIPTION_ONLY` | [`README.md`](/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/02_Stanford_LFP_SOC_2025/raw/README.md)，SHA-256 `78d184d50a6e7b4a99bd32ef7c25030a467b2b708e0c67b2dd42ceff55890593`，4,417 bytes。它描述论文 DOI 与预期 7 类目录，但不是实体 manifest 或固定发布版本。 |
| source/download manifest | `FAIL` | 候选根内不存在 manifest。 |
| 原始实体/清单/哈希 | `FAIL` | 候选根仅有 `LICENSE`、`README.md`；数据实体数为 0，故无 archive 文件名、大小或实体 SHA 可绑定。 |
| schema/header | `NOT_VERIFIABLE` | 无数据实体，无法取得表头；未尝试以 README 描述代替 schema。 |
| 禁用语义扫描 | `PASS（仅现有元数据）` | 仅扫描本地相对路径与可用 README/LICENSE 元数据，`rul/rul_cycles/rul_observed/eol/eol_*/trajectory/trajectory_*` 为 0 命中。 |
| 冻结根拒绝 | `PASS_METADATA_ONLY` | 控制台账 [`2026-08-09-frozen-rul-asset-denylist.json`](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json)，SHA-256 `44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`，版本 `2026-08-09.p0-2.1`、13 根；规范化候选根匹配数为 0。只读取控制台账，未读取冻结资产内容。 |

该本地目录无法承担 SOH 来源：缺数据实体是确定性失败，而许可证覆盖、版本、manifest 和 schema 同时不可复核。不得改用任何 RUL、生命周期、EOL 或 trajectory 资产补足。

## 缺口与最小下一步

仅由上层另行提供“现存本地原始数据实体 + 明确绑定该数据版本的许可证快照 + source/download manifest + archive 清单、大小与 SHA-256”。证据齐备后重新执行 SOH 独立来源门；当前不搜索、不下载、不创建候选。

## 只读命令与边界声明

使用：`find -maxdepth 2 -type f`（只列名）、`stat -f bytes=%z`、`shasum -a 256`、`sed` 读取 LICENSE/README、Python 仅解析冻结 denylist 控制台账并执行规范根/后代匹配。未读取样本行（0 行），未读取冻结 RUL/v11/v9/v10/`INVALIDATED` 资产内容，未改代码/配置/数据，未运行测试、烟雾或训练。

机器可读证据表：[`2026-08-09-soh-local-source-admission-evidence.json`](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-soh-local-source-admission-evidence.json)。
