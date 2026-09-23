# Zenodo 8381142 系统级 SOE 来源审计

## 裁定

`SYSTEM_LEVEL_SOE_SOURCE_PASS`。本来源仅定位为社区电池储能系统（CBES）的系统级状态量回归候选，不代表单电芯 SOE，也不能支持未知电芯泛化结论。此项来源裁定不等于数据版本或训练验收通过。

## 来源与实体

- 官方记录：<https://zenodo.org/records/8381142>
- 官方元数据 API：<https://zenodo.org/api/records/8381142>
- DOI：`10.5281/zenodo.8381142`
- 固定记录版本：`1.0`，发布日期：`2023-09-26`
- 许可证：`CC BY 4.0`（官方记录元数据 `license.id=cc-by-4.0`）
- 开放状态：记录与文件入口为公开访问；此次受控下载最终响应为官方 Zenodo `HTTP 200`，未发生跳转。
- 文件名：`UC Setting Data.csv`
- 官方字节数：`5,778,187`
- 官方 MD5：`5989bfac08cde0843acb53382b0abea7`
- 本地隔离路径：`/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/.source_quarantine/2026-09-22/soe_zenodo_8381142_v1/UC Setting Data.csv`
- 本地字节数：`5,778,187`；本地 MD5 与官方值一致。
- 本地 SHA-256：`1069010d122e2100b9edd427c070899374fd941e500e45efba222bb61d6e6475`
- 响应 Content-Type：`text/plain; charset=utf-8`；实体为 UTF-8 文本，CRLF 行结束。

## 内容范围与边界

官方描述将 `SoE` 定义为 use-case 提交时 CBES 的 state of energy；系统背景容量为 850 kWh。**SoE 原字段没有明确单位声明**，后续只保留原始数值名 `soe_source_value`，不推断 kWh、百分比或进行换算；850 kWh 仅作为来源背景信息，不作为单位证据或标签分母。

文件使用分号分隔、逗号小数格式。已确认的 23 个表头为：`RequID, Alert, Submission, Note, Priority, Status, Version, Start, End, Type, Subtype, bulkStart, bulkEnd, bulkEnergy, Final_SOF, FlexDemand, Ptcb, Ptei, SoC, SoE, ActiveSet, maxSoC, minSoC`。表头中 RUL/EOL/trajectory/lifecycle 禁用语义命中数为 0；该结论仅针对表头名称，不是对所有单元格文本的全量语义扫描。

核验记录称文件含 `28,740` 行、`313` 个 `RequID`；`SoE` 缺失和非数值均为 0，观察值范围为 `0.22–864.6`。这些计数将在数据适配器全量解析时再次计算；若复算不一致，不得发布 READY。首五条记录共享一个 `RequID` 与 `Submission`，但 SoE 值不同，因此这些行不是可据现有证据确认的逐时刻电芯轨迹。允许的目标仅为系统级逐记录 `SoE` 原值。

来源具有 `RequID`、`Submission`、`Start`、`End`、`Type`、`Subtype` 分组/时间字段；它们用于筛选、排序或审计，不作为模型特征。数据版本只允许将 `SoC`、`Ptcb`、`Ptei` 作为当行输入，将 `SoE` 作为标签；不得将 `Note`、`Final_SOF`、`End`、`bulkEnd` 或其他字段加入特征。

## 下载记录与范围声明

- 文件入口：<https://zenodo.org/api/records/8381142/files/UC%20Setting%20Data.csv/content>
- 下载命令使用 `curl --fail --location` 跟随官方链、无重试/代理/镜像；最终 `HTTP 200`，curl 退出码 `0`，下载大小 `5,778,187` 字节。
- 已完成 ZIP/归档检查不适用（来源实体为 CSV）；下载后确认实体大小和官方 MD5。
- 本次审计不读取其他数据源、不接触冻结资产，不创建模型或结果。

## 尚未由本审计放行

本报告只固定来源与实体边界。完整有效行数、筛选后 `RequID` 组数、80/20 组切分、manifest/READY 回读与原子发布由本目标后续数据门测试验证。数据版本通过之前，不得声称可训练；正式训练仍未获授权。
