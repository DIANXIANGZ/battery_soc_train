# NASA 经典老化档案 RUL 准入审计设计

## 目标

只判断 NASA PCoE 经典老化档案是否具备构建逐循环精确 RUL 标签的来源许可与物理 EOL 证据。本阶段不创建 v12、不修改 adapter/schema/数据、不提升 provenance、不训练。

## 顺序与停止条件

1. **许可先行**：仅从 NASA 官方数据目录、官方 Open Data 元数据/API 和官方使用条款取证。数据集级 `License not specified` 不等价于许可；只有明确绑定该数据集的许可或适用政府公开数据声明才通过。任何非 2xx、解析失败或适用性不明确立即停止整个 NASA 来源。
2. **协议后置**：仅在许可通过后，对既有 15 个 crossing 候选逐电芯验证 source file、README 试验组、EOL 阈值、容量单位、放电类型、连续 cycle 编号、相邻 above→below crossing 和异常容量规则。
3. **fail-closed**：任何字段不明，该电芯保持 censored；不得用 file-end、平滑、最后一次 crossing 或未来轨迹猜测补证据。

## 组件边界

- `src/research/nasa_classic_rul_audit.py`：纯函数验证来源许可快照和逐电芯协议记录；不依赖训练模块，不写数据目录。
- `tests/research/test_nasa_classic_rul_audit.py`：先 RED 后 GREEN，覆盖许可缺失、协议不一致、异常容量、非相邻 crossing 与合格 crossing。
- `docs/audits/`：保存官方许可快照指纹、逐电芯 CSV/JSON 和一页裁定；不保存模型或训练结果。

## 输出合同

审计结果必须包含 `training_authorized=false`、`v12_authorized=false`、逐电芯 `admitted_for_exact_rul`、blocker 列表、来源 URL/HTTP/ETag/Last-Modified/字节数/SHA-256、EOL 阈值与 crossing 上下界。许可失败时不生成任何通过电芯，只输出来源级 NOT_ADMITTED 裁定。

## 验收

- 许可门禁有可复核官方证据且 fail-closed。
- 若许可通过，每个候选都有一条可证伪、可复跑的协议审计记录。
- v11 manifest 与 cycles 哈希不变；本阶段新增训练产物为 0。
- 严格 RUL 继续 NOT READY，下一阶段必须再次获总工程师批准。

