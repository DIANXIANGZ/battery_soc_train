# SOT 既有本地来源门只读审计

日期：2026-08-09　目标：`SOT`　唯一结论：**NOT_VERIFIABLE**  
精确停止点：`LICENSE_VERSION_BINDING_NOT_VERIFIABLE`。部分实体门通过不能替代许可证/版本门，也不授权任何后续动作。

## 核验结果

| 门 | 结果 | 证据与解释 |
|---|---|---|
| 许可证 | `NOT_VERIFIABLE` | 四份 manifest 仅写 `Research/publication use with CALCE database and article attribution`，候选根没有独立许可证快照；该使用描述不能作为与实体绑定的固定许可文本。 |
| 版本 | `NOT_VERIFIABLE` | 四份 manifest 均写 `CALCE A123 archive, accessed 2026-08-03`；访问日期不是不可变发布版本。 |
| manifest/实体绑定 | `PASS` | 4/4 manifest 的 archive 路径、byte_count 与 SHA-256 和本地实体一致。完整绝对路径、manifest SHA、archive SHA/大小见机器表。 |
| 文件清单 | `PASS_WITH_NOTE` | 4 个 ZIP 共列出 8 个正常 XLSX 数据成员；0℃ ZIP 另含一个 `~$` 临时锁文件，未来若获授权须在 adapter 门显式拒绝/忽略并记录，不能当数据实体。 |
| schema/header | `PASS（表头级）` | 仅解析每个正常 XLSX 的 sheet 名和首行。8/8 均有 `Test_Time(s), Current(A), Voltage(V), Temperature (C)_1`；详细 header 在机器表。未读取第二行及后续样本。 |
| 禁用语义扫描 | `PASS` | 对 archive member 逻辑路径、download manifest 源实体字段、sheet 名和首行 header 扫描；`rul/rul_cycles/rul_observed/eol/eol_*/trajectory/trajectory_*` 为 0 命中。 |
| 冻结根拒绝 | `PASS_METADATA_ONLY` | 控制台账 [`2026-08-09-frozen-rul-asset-denylist.json`](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-frozen-rul-asset-denylist.json)，SHA-256 `44c5b5b1fe3bafb4d6c1e76d426f26d68a9868bf52c8ddeb31b33afde316d348`，版本 `2026-08-09.p0-2.1`、13 根；四个规范化候选根匹配数均为 0。只读取控制台账，未读取冻结资产内容。 |

四份 manifest 证据（绝对路径 → SHA-256）：

- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_0c/download_manifest.json` → `1284b0e56462be88f537f4da60db9f67ed3f0514ee5968282038bc05cdaab26b`
- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_25c/download_manifest.json` → `a170ba2a1dedd0c00b395996bfdb65f030b83cbd50f4c936f0c254c96b8fd678`
- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_50c/download_manifest.json` → `01ef948ac1048ea008134aa9ec4f371890b75f341222d1825f6b1f5a4848ad50`
- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/04_公开电池数据集/calce_a123_dynamic_temperature/download_manifest.json` → `2de6e50ccfee6f631ca7c305b04d2ba433c053966feb0cc93bb060acea0a2db6`

## 缺口与最小下一步

仅需上层提供本地、不可变且明确绑定上述四个 CALCE archive 实体的许可证快照，以及稳定的来源发布/version 标识。随后重新执行 SOT 独立来源门；不得以网页描述、访问日期或其他目标的准入代替。

## 只读命令与边界声明

使用：`find` 只列文件名、`stat`、`shasum -a 256`、`unzip -Z1` 只列 archive member、`sed` 读取 download manifest；Python `zipfile`/XML 仅取得 XLSX sheet 名与首行 header，并解析冻结 denylist 控制台账做规范根匹配。未读取第二行或任何样本行（0 行），未读取冻结 RUL/v11/v9/v10/`INVALIDATED` 资产内容，未改代码/配置/数据，未运行测试、烟雾或训练。

机器可读证据表：[`2026-08-09-sot-local-source-admission-evidence.json`](/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/docs/audits/2026-08-09-sot-local-source-admission-evidence.json)。
