# `zn82y35zr8` Version 4 严格 RUL 元数据准入结论

日期：2026-08-05（Asia/Shanghai）  
结论：**NOT_ADMITTED；只能视为 interval-censored 候选，不得用于 `<=1-cycle` 验收。**

本轮仅对官方公开记录 `https://data.mendeley.com/datasets/zn82y35zr8/4` 发起一次固定 URL 的 HTML GET；未跟随重定向、未重试、未调用需要 OAuth 的 API、未打开 file/download URL、未下载数据文件。

## 固定响应证据

- UTC 响应时间：2026-08-05 08:04:24
- 最终 URL：`https://data.mendeley.com/datasets/zn82y35zr8/4`
- HTTP / Content-Type：`200` / `text/html; charset=utf-8`
- Content-Length：129,494 bytes
- ETag：`W/"1f9d6-2ZgBPdOJrXBCLH32RPACbajseEI"`
- HTML SHA-256：`adc564ba3b1158f56bfd70a757515f82cda6f59d475992cf427058130632ad98`
- 响应 Link 绑定：DOI `10.17632/zn82y35zr8.4`；license `http://creativecommons.org/licenses/by/4.0`

## 五项可证伪结果

| 项目 | 结果 | 可复核证据与影响 |
|---|---|---|
| 1. 记录、版本、DOI、许可 | **PASS** | 页面显示 Version 4、2025-01-28、DOI `10.17632/zn82y35zr8.4`、`CC BY 4.0`；嵌入元数据给出完整名 `Creative Commons Attribution 4.0 International`，响应头同时绑定许可 URL |
| 2. 文件清单、字节、校验 | **FAIL / STOP** | HTML 文件树为动态 Loading，嵌入状态为 `files.list=[]`；公开页面没有可复核的文件级 ID、完整清单、字节数和 checksum。官方 Datasets API 文档要求 OAuth token；按禁止登录/受限 API 的门禁，不调用该 API，也不打开 file/download URL |
| 3. 60 电芯、阶段与 RPT cadence | **PARTIAL PASS** | 记录明确 60 个物理电芯；第一阶段 SOH100→SOH80，第二阶段 SOH80→SOH60；RPT 每 50–100 cycles，并说明逐电芯 RPT/Cycle/After-SOH80 CSV 组织方式。但因第 2 项失败，无法把 60 个 cell ID 与实际文件逐一绑定 |
| 4. 精确 EOL cycle | **FAIL（interval only）** | 官方记录只证明 SOH 通过每 50–100 cycles 的 RPT 检查，并将最高编号 RPT称为 EOL RPT；没有公开的逐 cycle EOL 字段或首个 capacity crossing cycle。Cycle 文件名虽声明包含起止循环号，但文件清单不可核验，不能用 file-end 推断 EOL |
| 5. 任务可分离性 | **PASS with restriction** | 第一阶段的阈值为 SOH80，第二阶段为 SOH60，且运行协议不同，必须作为两个独立区间删失任务；不得彼此混合，也不得与 MATR/Oxford 单一回归混合。当前允许单位仅为以物理 cycles 表示的 50–100 cycle 观察区间，不允许 `<=1-cycle` 点标签 |

## 裁定与下一步

该来源同时在文件实体门禁和精确 EOL 门禁失败，故停止本来源核验，不重试、不换镜像、不调用 OAuth API、不下载。它不能新建 v12，不能提升 provenance，也不能授权烟雾或正式训练。

若未来由用户直接提供官方 Version 4 数据包及随包文件清单/校验和，则仍必须先证明 60 个电芯逐一唯一映射，并证明 SOH80/SOH60 的首个物理 crossing cycle；若原始协议本质上只有 50–100 cycle 的 RPT区间，则永久只能用于独立的 interval-censored 任务，不能满足当前 `<=1-cycle` 标准。

v11 保持 `valid_for_training=false`、`training_authorized=false`，所有既有冻结不变。
