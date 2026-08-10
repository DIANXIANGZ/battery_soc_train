# Mendeley Knee V4 Interval-Censored RUL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立与严格点 RUL 完全隔离的 Mendeley Knee V4 区间删失 RUL 数据合同、准入器和可复核评估基础；本计划不授权训练。

**Architecture:** 新增 `src/interval_rul` 独立包，先验证来源实体，再将两个寿命阶段分别转换为整数闭区间标签，最后用纯函数门禁与合成数据验证 LOCO、校准和未来扰动不泄露。新产物进入独立 `mendeley_knee_interval_rul_v1` 目录，不读取或覆盖 v11。

**Tech Stack:** Python 3.12、pandas、NumPy、pytest；不导入 Torch/XGBoost。

## Global Constraints

- v11、严格点 RUL、MATR、Oxford、NASA 保持冻结；新区间任务不得报告点 MAE、`<=1-cycle` 或等价措辞。
- `soh100_to_80` 与 `soh80_to_60` 分别建表、LOCO 和评估；不共享拟合状态。
- 无总工程师下载批准不得获取文件；无测试工程师 PASS 不得申请数据版本或训练批准。
- 网络出现认证、401/403/429、TLS/非2xx、访问限制或不明重定向立即停止，不重试、不用镜像。

## 精确下载请求（当前未授权）

- 官方记录 URL：`https://data.mendeley.com/datasets/zn82y35zr8/4`
- 固定版本/DOI/许可：V4 / `10.17632/zn82y35zr8.4` / CC BY 4.0
- 唯一文件：`Battery raw data.zip`，页面显示约 1.38 GB
- 理由：核验 60 个物理电芯的 Cycle/RPT/After-SOH80 文件映射、实际 RPT bracket、两阶段终止与删失语义
- 磁盘预算：至少 4.5 GB（原包、只读解压、canonical/audit）；预计传输 10–60 分钟，视正常公开链路而定
- URL 规则：不得猜测直链；批准后只从上述官方 V4 页面解析该可见文件项。先记录响应链和最终 2xx，再读取正文
- 校验：记录官方 Content-Length/ETag/Last-Modified/UTC；下载后计算 SHA-256。若发布者未给 checksum，明确标注本地再现指纹，不冒充上游校验

---

### Task 1: 区间标签合同与 schema

**Files:** Create `src/interval_rul/contracts.py`; Test `tests/interval_rul/test_contracts.py`

**Interfaces:** `make_observed_interval(last_above_cycle: int, first_at_or_below_cycle: int, prediction_cycle: int, threshold_evidence: ThresholdEvidence) -> ObservedInterval`; `make_right_censor(last_above_cycle: int, prediction_cycle: int, threshold_evidence: ThresholdEvidence) -> RightCensor`; `classify_left_or_invalid(observations: tuple[RptObservation, ...], threshold_evidence: ThresholdEvidence) -> CensorAudit`; `validate_interval_frame(frame: pd.DataFrame) -> None`。

- [ ] RED：写测试并运行 `/opt/homebrew/bin/python3.12 -m pytest -q tests/interval_rul/test_contracts.py`，确认因模块不存在失败。

```python
def test_discrete_open_closed_eol_becomes_closed_rul_interval():
    y = make_observed_interval(100, 150, 40, evidence())
    assert (y.lower_cycle, y.upper_cycle) == (61, 110)

def test_prediction_inside_future_eol_bracket_is_rejected():
    with pytest.raises(ValueError, match="prediction_cycle must not exceed last_above_cycle"):
        make_observed_interval(100, 150, 101, evidence())

def test_right_censor_has_no_finite_upper_or_interval_loss():
    y = make_right_censor(150, 40, evidence())
    assert (y.lower_cycle, y.upper_cycle, y.training_eligible) == (111, None, False)
```

- [ ] GREEN：最小实现整数端点、`interval_observed/right_censored/left_censored/invalid_protocol`、两个固定 `stage_id`，拒绝缺字段、浮点/布尔 cycle、负宽度、SOH 参考不明和非官方 source/version/license。
- [ ] 回归：运行该文件并将输出交测试工程师；不创建数据目录。

### Task 2: V4 adapter 与逐电芯协议审计

**Files:** Create `src/interval_rul/adapters/mendeley_knee_v4.py`; Test `tests/interval_rul/test_mendeley_knee_v4_adapter.py`

**Interfaces:** `inventory_archive(root: Path, source_manifest: SourceManifest) -> ArtifactInventory`; `validate_bidirectional_mapping(inventory: ArtifactInventory, required_roles_by_stage: dict[str, tuple[str, ...]]) -> MappingAudit`; `build_interval_rows(inventory: ArtifactInventory, stage_id: str) -> pd.DataFrame`。

- [ ] RED：用纯临时夹具证明 artifacts 必填实体字段缺失、60-cell inventory 无法由实体证明、token 碰撞、重复/重叠 chunk、同一 artifact/path/content 跨 cell/阶段/角色复用、After-SOH80 未进入 MappingAudit、正反映射不互逆、官方 required-role matrix 缺失、file-end 伪 EOL、SOH 参考缺失和 RPT 非单调均使整个版本 INVALIDATED。
- [ ] GREEN：只解析批准后的本地只读解压目录；`MappingAudit` 对每个 `(cell,stage)` 输出 cycle/rpt/after_soh80 artifact IDs、C/R/A、异常列表和 valid。每阶段必需角色/文件基数及 After-SOH80 阶段归属只能由随包说明生成并记录 provenance，不能在代码中假定每 cell 各一个文件。
- [ ] 因果回归：修改未来 RPT/循环尾段，断言所有 `prediction_cycle` 前缀特征、区间下界来源和 split identity 不变。
- [ ] 验收命令：`/opt/homebrew/bin/python3.12 -m pytest -q tests/interval_rul/test_mendeley_knee_v4_adapter.py`；先交测试工程师 PASS。

### Task 3: 独立 corpus、manifest 与原子失效

**Files:** Create `src/interval_rul/build_corpus.py`; Test `tests/interval_rul/test_build_corpus.py`

**Interfaces:** `build_interval_corpus(raw_dir: Path, output_dir: Path, report_dir: Path) -> dict[str, object]`；输出 `interval_labels.csv`、`corpus_manifest.json`、`admission_audit.json`。

- [ ] RED：断言非空输出目录、来源不符、60-cell 映射不完整、阶段混合、unknown censoring、v11 路径、外部 source 行、无 license/hash 均 fail-closed，且失败前不留下半成品。
- [ ] GREEN：写临时目录后原子发布；manifest 初始 `valid_for_interval_training=false`、`interval_training_authorized=false`，只在全部数据门禁通过后允许前者为 true，后者始终等待单独批准。
- [ ] 失效：adapter/schema/source/hash 任一改变时写 `INVALIDATED.json`，保留证据，不覆盖旧版本；断言 v11 manifest/cycles SHA-256 仍为 `57c011de88fc9af88ac18808f6b2e22525c5979bd2f765c426a11516b09cf196` / `9a532700f2e0157eaa1172f85d0ef353cfb7f5b3bcc8ef40992961d82e778999`。
- [ ] 验收命令：`/opt/homebrew/bin/python3.12 -m pytest -q tests/interval_rul/test_build_corpus.py`；先交测试工程师 PASS，仍不得训练。

### Task 4: 区间指标、阶段独立 LOCO 与 admission

**Files:** Create `src/interval_rul/evaluation.py`; Create `src/interval_rul/admission.py`; Test `tests/interval_rul/test_evaluation.py`; Test `tests/interval_rul/test_admission.py`

**Interfaces:** `make_loco_folds(frame, stage_id) -> tuple[LocoFold, ...]`; `make_nearest_rank_baseline(train_labels, nominal_levels=(0.5, 0.8, 0.9)) -> pd.DataFrame`; `interval_metrics(labels, predictions, nominal_levels=(0.5, 0.8, 0.9)) -> dict[str, float]`; `assess_interval_training(manifest, audit) -> IntervalAdmission`。

**Result schema:** 每个 `(stage_id, fold_id, physical_cell_id, nominal_level)` 一行，固定字段为 `n_finite, compatibility_coverage, enclosure_coverage, mean_width, median_width, weighted_interval_score, empirical_enclosure_coverage, right_censored_n, right_censored_lower_bound_violation_rate, baseline_*`；另输出逐 cell/fold 等权的 stage 宏平均行，禁止按样本行数微平均。

- [ ] RED/GREEN 手算向量：两有限行 `Y1=[4,6],Y2=[10,12]`，90% 预测 `[3,7]`、`[11,13]`，必须得到 compatibility=1、enclosure=.5、mean/median width=3、WIS=3；50/80/90 enclosure=(.5,1,1) 时 ICE=.10。`Y=[4,6],P90=[7,9]` 得 WIS=4；非嵌套 `P50=[3,8],P80=[4,7],P90=[5,9]` 整 fold FAIL；right censor `[8,+∞),P90=[2,7]` violation=1且不进有限分母。
- [ ] GREEN：实现 `C/E/W/D/WIS=W+2D`、enclosure calibration、逐 cell/fold 等权 stage 宏平均和 right-censored violation；空有限 fold、缺失/非有限/不嵌套预测不得删行。
- [ ] 基线 GREEN：每 fold/stage 仅用训练有限行；nearest-rank `Q_p=x_(max(1,ceil(mp)))`，`Bα=[Q_q(L),Q_(1-q)(U)]`。训练 `[2,4],[4,6],[8,10],[10,12]` 在 α=.5 得 `[2,10]`；模型 `[3,7]` 对测试 `[4,6]` 严格胜出，模型等于 `[2,10]` 必须 tie FAIL。`m=0` 为 NOT_COMPARABLE。
- [ ] 门禁：结构/泄露 100% 通过；每 fold 及 stage 宏平均 compatibility@90 `>=.90`、ICE `<=.10`，且 mean width 与 WIS 都严格小于基线；相等/NaN/不可比较均 FAIL。
- [ ] 全量 freeze-safe：运行 `pytest -q tests/interval_rul`、`python -m compileall -q src/interval_rul tests/interval_rul`，静态搜索 `torch|xgboost|public_battery_corpus_v11|rul_cycles.*MAE`；证据提交测试工程师，未经 PASS 不申请下一阶段。

## 四类 RED 用例清单

1. **映射/实体**：After-SOH80、60-cell inventory、required-role provenance、F/G 双向唯一性、缺失/重复/碰撞/跨 cell/阶段/角色复用与 chunk 重叠。
2. **删失端点/路由**：observed/right/left/invalid 四种构造；整数/布尔/浮点边界；`t<=a<b`；file-end 非 EOL；right 的无限上界与 `training_eligible=false`；left/invalid 排除。
3. **指标/嵌套/分母**：A 包全部手算向量、50/80/90 嵌套、enclosure ICE、right-censored 有限分母排除以及缺失/非有限预测 fail-closed。
4. **LOCO 基线/可比性**：仅训练 cells、同 stage/fold、nearest-rank 常量区间、`m>=1`；空 fold、NaN、分母不一致、tie 或未同时严格改善 width/WIS 均 FAIL。

## 执行停止点

本计划获批后第一步仍是**下载准入**，不是代码或训练。下载实体及来源证据通过后，才按 Task 1→4 严格 TDD。Task 4 通过只代表 interval 基础设施可验收；真实烟雾/训练需要总工程师另行批准。
