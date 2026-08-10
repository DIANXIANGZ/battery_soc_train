# 自定义算法训练选项：只读范围清点

日期：2026-08-04  
范围：现有 UI、算法注册、项目持久化、训练调度、结果契约和数据门禁。  
本文件不构成实现或训练授权。

## 结论先行

原始“自定义数据集 + 算法选择”主链路已经存在，但目前只能视为**功能原型**：用户可导入 CSV/Excel、映射特征和目标、选择 LSTM/GRU/XGBoost/Transformer，并由后台子进程路由；然而现有入口没有把目标级数据准入、RUL observed/provenance、标签因果血缘、manifest 授权或严格留出作为启动前硬门禁。

因此当前允许优先交付的是配置能力：算法注册、算法选择栏、目标/字段映射、推荐说明、配置持久化、准入报告和禁用态 UI。实际训练启动必须继续阻塞；尤其不得以 v11 的 5 个 MATR observed 电芯启动 RUL 训练或烟雾。

## 现有功能清点

| 层 | 现有入口/接口 | 已具备 | 当前边界或缺口 |
|---|---|---|---|
| UI 数据集入口 | `src/desktop/app.py:192-196, 216-257` | 下拉框“自定义数据集…”、独立“导入自定义数据”按钮、CSV/XLSX/XLS 文件选择 | 算法只在导入弹窗选择，训练页没有独立的可复核配置栏或门禁状态 |
| 列映射 | `src/desktop/app.py:241-257` | 时间列、特征多选、目标多选 | 没有电芯/工况/会话/循环、`rul_observed`、`eol_provenance` 等非数值元数据角色映射 |
| 数据配置 | `src/custom_training/dataset.py:15-22` | `CustomDatasetConfig` 保存源、工作表、时间、特征、目标、算法 | 缺少标签单位、预测时刻、目标协议、来源 manifest、字段角色与训练准入状态 |
| 数据校验 | `src/custom_training/dataset.py:67-105` | 格式、列存在性、重复角色、数值转换、最少 30 行 | 仅做表格可读性；没有来源、单位、标签因果、未来扰动、删失或严格分组可行性门禁 |
| 算法枚举 | `src/custom_training/dataset.py:11-12`；`src/training/train_custom.py:22` | 四算法名称均为 `lstm/gru/xgboost/transformer` | 两处重复常量，存在 UI/校验/CLI 漂移风险；没有集中元数据、适用目标和运行约束 |
| 项目持久化 | `src/platform/platform_core.py:121-150` | 导入数据复制到独立项目并将 `custom_config` 写入 `projects.json` | 算法不可在训练页单独修改；修改算法后也没有自动使旧准入失效的机制 |
| 命令路由 | `src/platform/platform_core.py:297-316` | 安全参数列表调用 `src.training.train_custom`，传递算法/特征/目标 | 在创建 run 目录前没有检查 `valid_for_training`、`training_authorized` 或目标门禁 |
| 桌面调度 | `src/desktop/app.py:583-603`；`src/desktop/training_controller.py:37-73` | 自定义项目自动选用 `build_custom_command`，后台 `Popen`、日志和进度 | `TrainingController.start` 前没有不可绕过的 admission gate；当前 UI 能直接进入训练路径 |
| 切分 | `src/training/train_custom.py:44-97` | 同时存在 `cell_id` 和 `condition_id` 时使用严格分组；否则按时间 60/20/20 | UI 导出不会保留非数值 identity 元数据，常见自定义项目实际退化为 time-only；time-only 不能支撑跨电芯泛化声明 |
| 归一化 | `src/training/train_custom.py:119-128` | 只用训练分区拟合均值/标准差 | 这是必要但不充分的防泄露措施；尚无标签未来扰动、特征可用时刻或来源血缘审计 |
| XGBoost 隔离 | `src/training/train_custom.py:130-150`；`src/training/xgboost_backend.py:1-49` | 新解释器子进程、后端拒绝已加载 Torch、`nthread=1` | 必须保留；不得改回与 Torch 同解释器真实拟合 |
| 验收 | `src/training/train_custom.py:226-233`；`src/training/battery_protocol.py:132-186` | 标准目标输出 MAE、覆盖率和阈值判定 | 任意自定义数值标签会落入默认 `0.01` 绝对阈值，单位语义错误；必须在单位/阈值声明前阻塞“通过/失败”裁定 |
| 结果读取 | `src/platform/platform_core.py:390-418`；`src/desktop/app.py:702-801` | 历史运行列表与通用结果页面存在 | 完整运行识别偏向 SOC/五状态；自定义 target metrics 契约与 `n_test` 要求不一致 |
| 图表 | `src/desktop/charts.py:40-109` | SOC 曲线和训练/验证 loss 图 | 硬编码 `reference_soc`、`predicted_soc`、`validation_mse`；自定义非 SOC、XGBoost 或当前 `train_loss` 历史可能无法正确渲染 |

## 主要数据质量风险

| 发现 | 严重度 | 影响 |
|---|---|---|
| 自定义训练启动前没有 manifest/target admission 硬门禁 | Critical | 任意数值列可被当作可信标签并启动训练 |
| RUL 不要求 `rul_observed=1` 与受控 provenance | Critical | 右删失或文件终点可能被错误当作精确监督 |
| UI 未保留 identity/condition 元数据角色 | Critical | 严格未见电芯/工况切分通常不可达，窗口边界审计也可能失效 |
| 任意自定义目标默认采用 0.01 绝对误差阈值 | High | 不同单位下的“通过”结论没有语义 |
| 算法常量分散在 validator 与 trainer | Medium | 算法列表、显示名称、适用目标和隔离要求可能漂移 |
| 自定义结果读取和图表仍硬编码 SOC/五状态契约 | High | 即使训练产物存在，也可能被平台误判为不完整或渲染失败 |
| 训练页显示多项自定义命令未消费的 SOC 参数 | Medium | 用户会误以为参数生效，降低配置可解释性 |

## 目标级门禁依赖

以下是“可以保存配置”与“可以训练”的分界。配置不足时仍允许用户完成字段与算法选择，但必须显示阻塞原因并禁用运行。

| 目标 | 配置阶段可检查 | 训练前必须额外通过 |
|---|---|---|
| SOC | 电芯/会话/循环/工况/时间角色；电压、电流、温度和目标列；推荐 LSTM/GRU | 来源/单位、因果容量参考或可信标签血缘、未来尾段扰动不改变前缀、窗口不跨组、严格未见电芯/工况、train-only 预处理、manifest 授权 |
| SOE | SOC 条件、功率/电压/电流、能量目标和上述 group/time 角色；推荐 LSTM/GRU | 因果能量参考、单位一致性、未来扰动、严格留出、train-only 预处理、manifest 授权 |
| SOT | 当前温度、预测 horizon、group/time 角色；推荐 LSTM/GRU/Transformer | 目标确为预测时刻后的固定 horizon，未来温度不进入特征，标签不跨循环/会话，严格留出、manifest 授权 |
| SOH | cell/cycle、容量/曲线统计、目标列；小数据可推荐 XGBoost，长序列可推荐 Transformer | 初始容量基准只能来自允许的因果参考，当前/未来目标容量不能作特征，严格留出、单调/定义审计、manifest 授权 |
| RUL | cell/cycle、`rul_observed`、`eol_provenance`、EOL 定义和目标列；算法只作配置建议 | 精确监督仅允许 `rul_observed=1` 且 provenance/来源协议支持精确 EOL；右删失与 Oxford 100-cycle 网格不得进入点标签；至少具备可辩护的严格留出规模；manifest 授权 |
| 其他数值标签 | 目标列、单位、预测时刻、可用时刻、group/time 角色 | 标签语义、单位、因果可用性、验收阈值或仅报告指标的规则、严格留出和 manifest 授权；未声明前不得显示“通过” |

## 数据冻结下可交付的功能

这些功能不需要真实模型拟合，也不改变 v11 或任何公开电池数据：

1. 集中的四算法注册表：稳定 key、显示名、适用任务提示、序列/表格属性、XGBoost 隔离要求。
2. 自定义项目训练页的“算法配置”栏：查看、修改和保存算法；目标推荐仅作建议，用户可覆盖。
3. 标准字段角色映射：cell/session/cycle/condition/time、`rul_observed`、`eol_provenance`；导出时保留非数值元数据但不把它们作为模型特征。
4. 纯函数式 target admission 报告：逐目标列出已满足项、缺失项、泛化声明等级和阻塞原因。
5. 配置持久化：算法或字段映射一旦改变，已有 admission 自动失效并回到 `training_allowed=false`。
6. UI 禁用态：允许导入、映射、保存和查看报告，但“开始训练”保持禁用或在不可绕过的后台门禁处拒绝。
7. 命令预览/路由单元测试：只验证参数列表与隔离策略，不启动子进程、不拟合模型。
8. 自定义结果契约的只读 schema 校验设计；在训练解除前不生成新运行产物。

## 必须继续阻塞的运行行为

- 所有基于 v11 的 smoke/formal training。
- 以 5 个 MATR `official_continuation` 电芯启动任何 RUL 训练或声称 `<=1-cycle`。
- 36 个候选或 5 个早停的精确 RUL 点监督。
- Oxford 进入 1-cycle 点误差验收或与 MATR 混合平均。
- 缺少 `training_authorized=true` 与目标级门禁报告的任何自定义训练子进程。
- 缺少 cell/condition 严格分组时宣称跨电芯或跨工况泛化。
- XGBoost 与 Torch 在同一解释器内真实拟合。
- 未声明单位/阈值的自定义数值标签显示“验收通过”。
- 为验证 UI/路由而运行真实 LSTM、GRU、Transformer 或 XGBoost 拟合；本阶段测试必须使用纯函数、临时配置和 mock controller。

## 当前测试覆盖与缺口

现有覆盖：文件读取/数值校验、四算法真实最小拟合、未知算法拒绝、严格 group split、配置持久化、命令路由、UI 文本入口与推荐。

缺少的关键测试：

- 单一算法注册表驱动 validator、CLI 和 UI；
- 算法修改仅保存配置且使旧准入失效；
- RUL 缺少 observed/provenance 或来源协议时硬阻塞；
- v11 `valid_for_training=false` / `training_authorized=false` 时阻塞；
- Oxford 100-cycle-grid 不可用于 1-cycle point task；
- run 目录创建和 `TrainingController.start` 之前完成阻塞；
- metadata 角色导出保留 identity/provenance 且不要求数值化；
- 未知目标没有单位/阈值时只报告配置状态，不产生“通过”；
- XGBoost worker 保持无 Torch 导入与单线程配置；
- 自定义结果 schema 不再硬编码 SOC/五状态。

具体 TDD 任务和预计工时见 `docs/superpowers/plans/2026-08-04-custom-algorithm-admission-gated-configuration.md`。

## 2026-08-04 实施验收证据

本次只交付配置、UI、注册表与不可绕过的训练准入门禁；不构成任何目标的训练授权。

### TDD 断点

- Task 1 RED：`tests/test_custom_training_admission.py` 收集阶段因 `src.custom_training.admission` 不存在而失败（exit 2）。GREEN：`7 passed in 0.31s`。
- Task 2 RED：metadata role 未导出、`update_custom_algorithm` 不存在，`2 failed in 0.31s`（exit 1）。GREEN：`5 passed, 19 deselected in 0.19s`。
- Task 3 RED：命令、控制器和 UI 三层均未执行准入阻断，`4 failed in 2.06s`（exit 1）。GREEN：`8 passed, 43 deselected in 1.45s`。
- Task 4 首次全量检查：功能测试 60 项通过；一个既有 macOS 测试直接读取 Windows 专属 `subprocess.CREATE_NO_WINDOW` 而失败。经总工程师批准，仅将测试期望改为生产代码已经使用的 `getattr(..., 0x08000000)`；未修改生产行为。单项复验 `1 passed in 0.01s`。

### Freeze-safe 全量命令

```bash
/opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_custom_training_admission.py \
  tests/test_custom_dataset.py \
  tests/test_platform_core.py \
  tests/test_desktop_app.py \
  tests/test_desktop_training_controller.py \
  -k 'not algorithms_write_a_common_result_contract and not canonical_group_columns_enable_strict_cell_condition_split'
```

最终结果：exit 0，`61 passed in 2.10s`，0 skipped。未运行 `run_training`、真实模型拟合、烟雾、正式训练、数据下载或公开语料重建。授权命令预览只在 pytest 临时目录内创建空运行目录，随临时目录自动清理；共享工作区未生成模型、日志或持久运行目录，v11、标签、RUL provenance、阈值、训练设置和历史结果均未改变。

### 绕过与隔离检查

- `build_custom_command` 在 `create_run_dir` 前调用持久化 admission 硬门禁。
- `TrainingController` 对自定义命令缺失 admission 或显式非授权 admission 均在 `subprocess.Popen` 前拒绝。
- UI 禁用态不是唯一保护；算法保存会立即使旧 admission 失效。
- 静态回归确认 XGBoost worker 不导入 Torch、拒绝已加载 Torch、使用 `nthread=1`，父进程继续通过 `python -m src.training.xgboost_backend` 隔离调用。
- v11 冻结、MATR 仅 5 个精确 observed 电芯、Oxford 100-cycle interval grid 均继续得到 `training_allowed=false`。

### SHA-256

```text
cf29df66f2d8175e0052d41455462d1d691d9053ac6805fd72fd9d1cc515229b  src/custom_training/algorithms.py
e0ef115ce14febb274107410dc4aa0d741def78d36c5a227f9f187eaf3538937  src/custom_training/admission.py
e459d28638b2d204f6f767a3ed5ae80483adc277c6efba91545c690973539adf  src/custom_training/dataset.py
ba42ec866462b260d613781449b984fdee02bf3e1772079884ae2da21b3af04b  src/training/train_custom.py
e033d217fd1a5e0f850c10ed9fe41bb3eda22929d827033182c4225ca10c5fbe  src/platform/platform_core.py
d85dde2fa2e2404db8ca945ca31e3368dd1facca23bd7d42dc2daee80357b970  src/desktop/app.py
8e78379a1e20b8763d2786179265c581da5e2d9b26033b3487b98bc9577492bd  src/desktop/training_controller.py
c9d54a9f97b996f5bb11031ed7311691c6fbb8041c37ed8fc6313bfe5ad472e0  tests/test_custom_training_admission.py
4e32130cf588979619dba0372926e961038271ab09ad821fb0d659cb5e1de6ad  tests/test_custom_dataset.py
f776444bea50edb726b85902c1f8f7610cf50cb2c1fd14b59f214f908620b643  tests/test_platform_core.py
0ee1e010432dbeb5cdf94f28634e5d603d340f0aece71dd1d6ef608510acb2a3  tests/test_desktop_app.py
a8d871dcb2cd40914e148f80833a04737ca49b3412da33f3b19ec9e507cae524  tests/test_desktop_training_controller.py
```

## 2026-08-04 capability 硬化最终复验（取代上一节旧状态）

上一节 `61 passed` 与对应哈希只代表首轮实现断点。其后独立审阅发现并修复了 custom 路由降级、boolean-only admission、配置/数据过期、CLI 直达、manifest 畸形、角色列声明与真实导出不一致、严格泛化静默退化等 fail-closed 缺口。本节是当前实现的最终证据。

### 最终 freeze-safe 命令与结果

```bash
/opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_custom_training_admission.py \
  tests/test_custom_dataset.py \
  tests/test_platform_core.py \
  tests/test_desktop_app.py \
  tests/test_desktop_training_controller.py \
  tests/test_custom_cli_admission.py \
  -k 'not algorithms_write_a_common_result_contract and not canonical_group_columns_enable_strict_cell_condition_split'
```

结果：exit 0，`76 passed, 2 subtests passed in 2.24s`。

```bash
/opt/homebrew/bin/python3.12 -m compileall -q \
  src/custom_training src/platform/platform_core.py src/desktop/app.py \
  src/desktop/training_controller.py src/training/train_custom.py \
  tests/test_custom_training_admission.py tests/test_custom_dataset.py \
  tests/test_platform_core.py tests/test_desktop_app.py \
  tests/test_desktop_training_controller.py tests/test_custom_cli_admission.py
```

结果：exit 0，无输出。静态搜索同时确认：自定义命令在 `create_run_dir` 前验证 capability；Controller 在 `Popen` 前复核 registry/project/data/config/capability；CLI 在 `run_training`、数据读取和结果写入前复核；XGBoost worker 继续不导入 Torch、拒绝已加载 Torch 且 `nthread=1`。

明确排除：`tests/test_train_custom.py::CustomTrainingTests::test_algorithms_write_a_common_result_contract`、`tests/test_train_custom.py::CustomTrainingTests::test_canonical_group_columns_enable_strict_cell_condition_split`、任何真实 `run_training`、烟雾、正式训练、下载或语料重建。CLI 正路径只到 mocked `run_training` 边界。测试只在 pytest 临时目录创建并清理配置/空预览目录；共享工作区没有新增模型、训练日志或运行目录。v11、标签、RUL provenance、阈值、训练设置和历史结果均未改变。

### 当前 SHA-256

```text
cf29df66f2d8175e0052d41455462d1d691d9053ac6805fd72fd9d1cc515229b  src/custom_training/algorithms.py
7090532a257b9e5c20e21e3e551d1b624a5a480031e3db23b9076b1792d366fe  src/custom_training/admission.py
e52f70be307b3eb64afe0b3a4cf7fb446045375cfee60c0c644d34f3e019868a  src/custom_training/capability.py
e459d28638b2d204f6f767a3ed5ae80483adc277c6efba91545c690973539adf  src/custom_training/dataset.py
faf903bbe4e72a3d0d912d3ee9e2e271c97bd759e4c6e68137b8d547fb0bc2c6  src/training/train_custom.py
7cf46bb020b750c61a902c7ba619dee41ee43cc8dfc0e3921a1f5c4f5a796d9c  src/training/xgboost_backend.py
0d7f3a2ce4ec54a0860cf3d37c70f797dbd0893942d7c6eb22b5faa104150000  src/platform/platform_core.py
416720619e08c314aaa01d153e08637e67740f261b97d5630a63b76a7d2f807d  src/desktop/app.py
9f0ecb8e17e90d4cedc087c38d36056ad0bc50a782968619a835c107457993f9  src/desktop/training_controller.py
31a95437f9a12ab5a450bfadf750c8eb8caa5759b5349c94e0d7b8ce9ac01443  tests/test_custom_training_admission.py
4e32130cf588979619dba0372926e961038271ab09ad821fb0d659cb5e1de6ad  tests/test_custom_dataset.py
5f7fc527244065f64a08a46ca9e907a0e78b4d0cae83715208890a6a52049db0  tests/test_custom_cli_admission.py
50b137b53a5f2602ea69c4251ac469e7ce0733cb41941a0e45fa6512ce7e2c9b  tests/test_platform_core.py
ceb31d345a5f7827585f1a16bff29db4134674960bc8bd30698ba7530b3d0f3a  tests/test_desktop_app.py
8993933a1d39f42ae07dd93e121731933b9909088e5da52c66d7fbcece8cdc58  tests/test_desktop_training_controller.py
```

最终独立只读审阅结论：运行实现无 Critical/Important；审计证据刷新后满足本次配置/UI/注册/capability/门禁交付条件。此结论不授权任何真实训练，严格 RUL 训练验收仍受外部数据规模与协议阻塞。
