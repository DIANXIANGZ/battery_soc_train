# SOC/SOE/SOH/SOT 逐目标只读预检

日期：2026-08-09（Asia/Shanghai）  
范围：第 1 检查点；只读准入预检，不是技术准入、烟雾或训练验收。

## 总裁定

| 目标 | 独立裁定 | 可申请最小烟雾 | 首要阻断 |
|---|---|---:|---|
| SOC | **FAIL** | 否 | A123 标签使用完整循环范围，预测时刻非因果；且缺少 `cell_id`、`condition_id`、版本化来源/许可 manifest 和已固化严格 split |
| SOE | **FAIL** | 否 | 唯一已定位多状态候选表头含 `rul_cycles`，触发 RUL 零容忍拒绝 |
| SOH | **FAIL** | 否 | 同上 |
| SOT | **FAIL** | 否 | 同上 |

没有“整体 PASS”。四个目标均不得提交烟雾申请。物理参考、标签计算、静态列检查均未被表述为学习模型通过；学习模型层检查统一为 `NOT_VERIFIABLE (not executed)`。

## 共同边界与 INVALIDATED 拒绝

以下 v9/v10 失效标记均存在，因此两个版本对 SOC/SOE/SOH/SOT 全部拒绝。本次只核对标记路径及文件大小，未读取其数据或审计内容：

- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/04_公开电池规范数据/public_battery_corpus_v9/INVALIDATED.json`（1,110 bytes）
- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/04_公开电池规范数据/public_battery_corpus_v10/INVALIDATED.json`（1,070 bytes）
- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/05_公开电池数据质量报告/public_battery_corpus_v9/INVALIDATED.json`（1,110 bytes）
- `/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/05_公开电池数据质量报告/public_battery_corpus_v10/INVALIDATED.json`（1,070 bytes）

## SOC

### 候选与来源状态

- 候选：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/01_A123#3_SOC_30秒训练数据/a123_soc_30s.csv`
- 派生表：17,581,924 bytes；SHA-256 `8795e3f31e635e6b1bc6f95f2fc7d5097b47d9e6261bac781cf1d47886ed3`。
- 上游归档：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/01_原始数据/01_CALCE_A123#3_原始压缩包/A123_3_part1.zip`；1,002,988,515 bytes；SHA-256 `04edc3cce6eaf76b1317fa822bc15a6f219caa4d52cf0921d657fadb60a66bbb`。
- `configs/research/datasets.json:4-8` 仅登记 dataset、chemistry、role、Windows source path 和 `offline_cycle_range`；没有版本、明确许可证、下载记录或与上述 SHA 绑定的 manifest。因此 source/download manifest、license、version-bound hash 为 **FAIL**。单独计算的哈希不能替代版本化来源合同。

### 表头、标签和角色

- 列：`session, cycle_index, time_s, voltage_v, current_a, dv_dt_v_s, soc`。
- 248,502 行；6 个 session；178 个 `(session, cycle_index)`；上述列缺失值均为 0。`soc` 范围 `[0,1]`。
- 标签单位：fraction。`数据说明.md` 明确其为库仑计量参考、非独立物理真值。
- `src/data_processing/prepare_a123_soc.py:72-112` 先遍历完整循环得到 `net_range[cycle]` 的最小/最大值，再对同一循环每个时刻用该完整范围计算 SOC。这使早期时刻标签依赖未来循环观测，预测时刻语义不因果，故标签/因果门 **FAIL**。
- `session` 可承担 session role，`cycle_index` 可承担 cycle role；但 `cell_id` 和 `condition_id` 均不存在。角色本身未与目标列重叠，但必要角色不完整，角色门 **FAIL**。
- 既有设计文档提出六会话轮换留出（`docs/superpowers/specs/2026-07-18-generalization-first-optimization-design.md:22-24,66-68`），但候选表没有 cell/condition 列，也没有逐行固化 split 证据。因此 cell/condition 严格留出门 **FAIL**，文档设计不能替代数据级 split 证据。

### 泄漏与 RUL 零容忍

- 路径、表头以及只选取的 A123 非 RUL registry 元数据中，`rul`, `rul_cycles`, `rul_observed`, `eol_*`, `eol_provenance`, `trajectory_*` 为 0 命中：该候选的 RUL 零容忍字段门 **PASS**。
- 但完整循环标签构造已构成未来信息依赖；特征归一化、窗口构造、模型选择及运行时跨折依赖未执行，均为 **NOT_VERIFIABLE (not executed)**。
- v9/v10 失效不直接覆盖该 A123 路径，但该候选因上述独立门禁失败而不可用。

### 最小修复/证据需求

需要一个不覆盖现有文件的候选版本：提供明确许可证与来源/下载 manifest（版本、URL、大小、SHA）；以预测时刻仅可见的前缀和固定先验容量生成因果 SOC 标签；提供不与目标/特征重叠的 `cell_id/condition_id/session_id/cycle_id`；固化 cell 与 condition 双重严格留出；再做未来尾段扰动不改变前缀标签、训练折拟合隔离和 RUL 零命中回归。未经新授权，本次不实施。

## SOE

- 已定位候选：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/02_NASA_五状态训练数据/nasa_randomized_multistate_samples.csv`。
- 仅读取表头即发现：`cell_id,cycle_id,time_s,split,source_file,voltage_v,current_a,temperature_c,dv_dt_v_s,soc,soh,soe,rul_cycles,sot_c`。
- `rul_cycles` 命中 1 次，故 RUL 零容忍门 **FAIL**。按 fail-closed 规则立即停止：未读取样本行，未读取该目录的 `data_audit.json`、`split_manifest.json`，也未用其 source/label/role/split 元数据作任何推断。
- 因候选先被拒绝，source/license/hash、SOE 标签单位与 prediction-time 语义、角色完整性、严格留出、未来泄漏均为 **NOT_VERIFIABLE**；模型层为 **NOT_VERIFIABLE (not executed)**。
- v9/v10 另行全体拒绝。当前没有可独立准入的 SOE 候选，裁定 **FAIL**。
- 最小需求：提供完全不含 RUL/EOL/trajectory 字段、样本、授权或特征元数据的独立 SOE 导出，并提交版本化许可/哈希、因果能量标签合同、完整角色与 cell/condition 严格 split 证据。

## SOH

- 候选及表头与 SOE 相同；`rul_cycles` 命中 1 次后立即停止，未读取任何样本行或相邻审计/配置。
- 因而来源、标签定义（包括容量参考是否只来自可允许时刻）、`cell_id/condition_id/cycle_id` 角色、cell/condition 严格留出与未来泄漏均 **NOT_VERIFIABLE**；RUL 零容忍门 **FAIL**；模型层 **NOT_VERIFIABLE (not executed)**。
- v9/v10 另行全体拒绝。当前没有可独立准入的 SOH 候选，裁定 **FAIL**。
- 最小需求：提供无任何 RUL/EOL/trajectory 内容的独立 SOH 导出；绑定版本/许可/hash；明确额定或前置固定容量基准，禁止当前/未来目标容量；提供完整角色、逐行 split 与仅训练折统计证据。

## SOT

- 候选及表头与 SOE 相同；虽然存在 `sot_c` 和 `temperature_c`，但同表含 `rul_cycles`，整个候选按零容忍规则拒绝，不能通过删列绕过。
- 来源、摄氏度单位及预测时刻含义、`cell_id/condition_id/session_id/cycle_id` 角色、严格留出、目标与输入温度是否重叠、未来泄漏均 **NOT_VERIFIABLE**；RUL 零容忍门 **FAIL**；模型层 **NOT_VERIFIABLE (not executed)**。
- v9/v10 另行全体拒绝。当前没有可独立准入的 SOT 候选，裁定 **FAIL**。
- 最小需求：提供物理上独立且无 RUL 内容的 SOT 导出，区分预测时刻输入温度与未来目标温度，绑定来源/许可/hash，补齐角色和 cell/condition 严格 split，并证明前缀因果性及跨折拟合隔离。

## 只读命令与变更声明

使用的只读方法：`find/stat` 定位文件与大小；`head -n 1` 读取 CSV 表头；Python `csv.DictReader` 仅统计已确认无 RUL 表头的 A123 SOC 表；`shasum -a 256` 计算 A123 派生表/源归档指纹；`sed/nl/rg` 读取 A123 非 RUL 生成代码、registry 和设计证据。NASA 表头命中后未执行后续读取。

本次未读取或写入任何 RUL 数据、标签、配置、审计或历史产物；未修改任何代码、配置或数据；未创建导出、manifest 或数据版本；未运行 pytest、任何测试、烟雾或训练。唯一新增产物为本报告及配套元数据 CSV。
