# 严格 RUL 开放来源目录审计

日期：2026-08-04（Asia/Shanghai）  
状态：**没有可新建 v12 的来源；严格 RUL 仍为 NOT READY。**

## 永久准入规则

精确 RUL 来源必须同时满足：

1. 具体数据版本具有明确、可复核的开放许可证；
2. 官方来源可直接正常访问，或本地已有官方实体及许可证快照；
3. 电芯身份、逐循环记录、物理 EOL 定义和终止 cycle 均可追溯，且分辨率足以支持 `<=1 cycle` 验收；
4. 未通过的对象继续作为 `right_censored` 或区间诊断，不得因配置文件标记为 `approved` 而自动准入。

禁止绕过防火墙、403、访问控制、登录、反爬、重定向下载限制或其他技术限制；禁止镜像替代。许可证未明确时，不下载、不训练、不纳入 v12。

## 来源矩阵

| 来源 | 许可证门禁 | 直接/本地访问门禁 | 精确 EOL 门禁 | 裁定 |
|---|---|---|---|---|
| MATR Batch1/2 | PASS：已保存的官方项目证据显示 CC BY 4，Batch2 manifest 同样记录 CC BY 4 | PASS：本地固定实体和来源指纹已审计 | FAIL：当前仅 `b1c0`–`b1c4` 五个官方续接电芯可作精确 observed；36 候选与 5 早停仍为右删失 | 保留现状；规模不足，不建 v12、不训练 |
| Oxford degradation | PASS：本地 manifest 记录 ODbL 1.0 | PASS：本地固定实体 | FAIL：8 电芯、519 观测，中位采样网格 100 cycles，EOL 区间宽 100–200 cycles | 仅 interval-censored / 100-cycle-grid 诊断，禁止 1-cycle 验收 |
| Stanford LFP SOC 2025 | PASS：本地随包 MIT LICENSE | PASS：本地固定实体 | FAIL：SOC/工况与容量测试，不是逐循环寿命终止档案 | 可用于其原任务审计，不能承载精确 RUL |
| NASA PCoE 经典老化 | FAIL：官方目录字段为 `License not specified`，本地包无绑定许可证快照 | FAIL：唯一受控官方请求 curl exit 35、HTTP 000，无响应实体 | 未执行：许可门禁已先失败 | NOT_ADMITTED；停止，不重试、不下载、不做协议 TDD |
| NASA randomized | FAIL：现有配置中的通用“美国政府作品”描述不能替代具体数据版本许可证 | 未形成合规的本地许可证绑定 | 未准入审计 | 排除 |
| BatteryLife / Zenodo 21149533 | FAIL：配置中的“Open Zenodo dataset”是描述而非可验证许可证标识；官方记录元数据未取得 | FAIL：对 `https://zenodo.org/api/records/21149533` 的唯一元数据 GET 于 2026-08-04T14:17:36Z 在 TLS 阶段失败，curl exit 35、HTTP 000，无实体 | 未执行 | 来源停止；不换客户端、镜像或端点，不下载文件 |
| CALCE | FAIL：现有“Research/publication use...”为使用描述，未保存明确许可证快照 | 本地有部分数据，但不能弥补许可证缺口 | 现有动态工况来源不能证明寿命 EOL | 排除 |
| Sandia | FAIL：现有“Public research repository...”为描述，未保存明确许可证快照 | 本地工作簿不能建立权威终止语义 | FAIL：缺少唯一电芯/终止映射 | 排除 |

## 配置风险

`configs/research/public_battery_sources.json` 中的 `status: approved` 不是新的来源准入凭证。该文件部分条目仅包含描述性许可文本、空校验值或尚未复核的端点；在后续另行批准的 TDD 中，应让目录准入以“许可证实体指纹 + 官方来源身份 + EOL 证据合同”为准，并对上述弱证据 fail-closed。本次只读阶段不修改该配置。

## 影响与下一步

- 当前没有来源同时通过“明确许可证、直接/本地可验证访问、足够规模的逐循环物理 EOL”三项门禁。
- v11 保持 `valid_for_training=false`、`training_authorized=false`；不改变 adapter、schema、标签、provenance、阈值或历史结果。
- 不创建 v12，不运行烟雾、正式训练或真实拟合。
- 最小可执行下一步是等待一个本地随包携带明确许可证且具有逐电芯、逐循环 EOL 合同的官方数据源，或由总工程师批准审计一个可直接 2xx 访问并明确显示许可证的新官方目录。任何新来源仍须先完成纯只读准入审计，再申请 TDD 接入。

关联证据：

- `docs/audits/2026-08-04-nasa-classic-license-snapshot.json`
- `docs/audits/2026-08-04-nasa-classic-rul-cell-matrix.csv`
- `docs/audits/2026-08-04-nasa-classic-rul-admission-final.md`
- `docs/audits/v11_rul_final_data_admission.md`
- `docs/audits/v11_matr_composite_official_source_binding.json`
- `docs/audits/v10_oxford_rul_observability.json`
