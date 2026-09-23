# system_soe 数据门与版本构建记录

日期：2026-09-22（Asia/Shanghai）

## 结论与范围

`system_soe-baseline-v1` 已由 `build_version` 单次创建，并经 `verify_version` 回读验证（错误列表为空）。这是社区储能系统数据上的系统级基线，不是电芯级 SOE 数据，也不支持未知电芯泛化。SoE 标签保留来源原值，单位标记为 `unspecified_source_unit`，未推断为 Wh、kWh 或百分比。

## 来源与解析结果

- 来源：Zenodo 8381142，Version 1.0，DOI `10.5281/zenodo.8381142`，来源页面标示 CC BY 4.0。
- 来源证据：`docs/audits/2026-09-22-zenodo-8381142-system-soe-source-audit.md`，SHA-256 `6ec5dd42528d9dde9cd2c5762ad2cf92be2801419b00f6b3089b583f2b4a34d5`。
- 实体：`.source_quarantine/2026-09-22/soe_zenodo_8381142_v1/UC Setting Data.csv`，5,778,187 bytes；MD5 `5989bfac08cde0843acb53382b0abea7`；SHA-256 `1069010d122e2100b9edd427c070899374fd941e500e45efba222bb61d6e6475`。
- 全量解析统计：28,740 原始数据行；26,138 行接受；2,602 行拒绝（2,238 行 `invalid_numeric_feature`，364 行 `invalid_submission`）；313 个原始 RequID；298 个有效分组；SoE 缺失/非数值计数均为 0；标签来源值范围 0.22–864.6。
- 特征仅为当前行 `SoC`、`Ptcb`、`Ptei`。`Submission` 用于确定 RequID 的最早时间排序，不作为模型特征。RequID 是请求分组，不是电芯或时序会话。
- 切分：按最早 UTC Submission、再按 RequID 排序；前 `floor(0.8 × 298)=238` 组训练，余下 60 组测试；训练 21,205 行、测试 4,933 行，无验证集、无早停。

## 配置与构建器修复

- 配置禁词扫描现在跳过已由独立路径校验处理的 `source.source_csv` 和 `dataset.output_root` 值；其他配置字段和来源表头禁词检查未放宽。默认合法配置测试保留；非路径 `scope` 含 `lifecycle` 仍被拒绝。
- 适配器目标元数据包含固定回滚声明。构建器原校验未接受该字段；先补充测试并观察到 `system_soe目标元数据字段集合无效` 的 RED，再增加严格回滚声明校验，构建器回归转为通过。
- 相关文件 SHA-256：
  - `src/data_processing/non_rul_baseline/system_soe.py` — `cd4d06d349eca36e8e15b76274068e62d74f1419322c13643e4dde808e3b4450`
  - `src/data_processing/non_rul_baseline/build.py` — `14667a3ec400dd2114feb55ec76c07feb35d4fe583682690204228c0c8ca5f9b`
  - `tests/non_rul_baseline/test_system_soe_adapter.py` — `61b3f66b082a9407fe5f4a30143ce405bdee7c253bf0e1218a18761206ab36f2`
  - `tests/non_rul_baseline/test_system_soe.py` — `54d320e9f8e0d8be7450bb49273f5ba77fa19d47d29b7ae7dd4812e433cd2253`
  - 配置 `configs/training/non_rul_baseline/system-soe.json` — `445bfd096701c6b6620f2ea01c2cd3d7661418985c29953bfa3a626d024ebba1`

## 验证记录

- RED：默认配置因合法 `非RUL` 路径被误拒；修复后默认配置通过。非路径禁用语义仍拒绝。
- RED：带固定回滚声明的构建元数据被旧构建器拒绝；修复后完整构建器用例通过。
- 回归命令：`PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/non_rul_baseline/test_system_soe.py tests/non_rul_baseline/test_system_soe_adapter.py tests/non_rul_baseline/test_common_contract.py tests/non_rul_baseline/test_build_version.py` — 125 passed，exit 0。
- 编译：`PYTHONPYCACHEPREFIX=/private/tmp/system-soe-pycache-final /opt/homebrew/bin/python3.12 -m compileall -q src/data_processing/non_rul_baseline/common.py src/data_processing/non_rul_baseline/build.py src/data_processing/non_rul_baseline/system_soe.py tests/non_rul_baseline/test_system_soe.py tests/non_rul_baseline/test_system_soe_adapter.py` — exit 0。
- 空白检查：`git diff --check`（仅上述相关路径）— exit 0；未执行 Git 写操作。
- 构建/回读：目标路径构建前不存在；`build_version` 单次调用完成；`verify_version` 返回 `[]`。后续独立只读回读命令 exit 0。
- 构建包装命令最终 exit 1 的原因是报告输出代码读取了 manifest 中不存在的顶层 `source_files` 键；版本创建及当次 `verify_version` 已在该读取前完成。`source_files.csv` 是独立版本文件，后续只读回读确认其来源路径、字节数和 SHA 与来源实体一致。没有重跑构建。

## 版本工件

版本目录：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/system_soe-baseline-v1`

目录内仅有 `samples.csv`、`manifest.json`、`source_files.csv`、`READY.json`：

| 工件 | 字节数 | SHA-256 |
|---|---:|---|
| `samples.csv` | 3,921,789 | `d6abe22b5b3040bb39977263bfb40f1e2e77106f6e9ab7e600784513ee0b0e8e` |
| `manifest.json` | 45,650 | `72c4cb27e018c8e6fc592fe924ef79316dd29b175a6f51c6d06bf39dc4570a90` |
| `source_files.csv` | 236 | `8e4ef51edcf3e74d1ab5cd2bc77a734b14335dd31b04f192a64995e3f35b1601` |
| `READY.json` | 106 | `c18455709c3c7977e2c81ebcca95bf4d4de427f117d820a5f515fe44d2c6d6cf` |

## 边界

未运行烟雾或正式训练；未触碰 SOC/SOH/SOT、RUL、v9/v10/v11 或其他冻结资产；未下载来源；未改写既有版本；未执行 Git 写操作。该交付仅为 system-level SOE 数据准备版本，不代表训练或模型验收通过。
