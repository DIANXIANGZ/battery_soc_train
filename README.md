# A123#3 动力电池 SOC 估计

这是一个使用 CALCE A123#3 动态工况数据和 PyTorch LSTM 估计 SOC 的项目。

## 工程与数据分离

PyCharm 只打开本目录，它只保存代码、测试、配置、脚本和文档。

所有数据资产都在：`E:\SOC电池数据中心\`

| 数据目录 | 内容 |
|---|---|
| `01_原始数据` | 原始 CALCE 压缩包 |
| `02_训练数据` | A123#3 的 `a123_soc_30s.csv` |
| `03_模型与实验结果` | 基准模型、指标、图表及跨电芯评估结果 |
| `04_训练平台运行记录` | 桌面训练平台登记和全部历史运行 |
| `05_外部评估数据` | A123#5、CX2_4 的原始、解压和处理后数据 |

数据中心中的 `迁移清单.json` 记录了每个迁移文件的 SHA-256。

## 代码结构

```text
src/
├── data_processing/   # 原始数据检查、样本合并、SOC 标签构建
├── training/          # LSTM 训练与环境检查
├── evaluation/        # 预测分析与跨电芯评估
├── desktop/           # Tkinter 桌面训练平台
├── platform/          # 项目、训练与结果管理核心层
└── project_paths.py   # 数据中心路径的唯一读取接口
```

数据中心根路径在 `configs/paths.json` 中配置。不要把绝对数据路径直接写进训练、评估或平台代码。

## 常用命令

在项目根目录运行：

```powershell
..\..\work\soc_venv\Scripts\python.exe -m src.training.verify_pytorch
..\..\work\soc_venv\Scripts\python.exe -m src.training.train_lstm
..\..\work\soc_venv\Scripts\python.exe -m unittest discover -s tests -v
scripts\初始化环境.bat
scripts\启动训练平台.bat
```

首次使用时双击 `scripts\初始化环境.bat`，它会在本项目创建隔离的 `.venv`。以后双击 `scripts\启动训练平台.bat`，即可打开独立的 Windows 窗口；不使用浏览器或端口。

命令行显式传入 `--data`、`--results-dir`、`--model` 或 `--input-dir` 时，会覆盖配置中的默认数据位置。

## 标签与结果解释

SOC 标签由每个循环内的库仑计量构建，是训练参考标签，不是独立测得的物理真值。A123#5 的跨电芯结果是冻结 A123#3 模型在未见会话上的独立评估，不能与 A123#3 基准结果混合或覆盖。

## 防止过拟合的训练机制

新的默认训练策略会主动抑制过拟合：隐藏层大小为 32，预测头使用 0.10 Dropout，优化器使用 AdamW 和 `1e-4` 权重衰减；验证误差连续 3 轮停滞后学习率减半，最低降至 `3e-5`；梯度范数限制为 1.0。早停等待 9 轮，并要求验证 MSE 至少改善 `1e-5` 才算真正进步。训练停止后仍恢复验证误差最低时的权重。

每次训练的 `training_history.json` 同时记录 `training_mse`、`validation_mse` 和 `learning_rate`。桌面平台生成的 `validation_loss.png` 会同时显示蓝色训练曲线和紫色验证曲线：训练误差继续下降、验证误差持续上升并且间距扩大，才是典型的过拟合信号。

这些机制只使用 A123#3 的训练与验证会话。A123#5 仍只用于最终跨电芯检查，不参与调参或早停。

## 综合泛化验证

完整实验使用五个随机种子和六轮留一工况验证。只有五种子平均 MAE 不高于 3.5%、留一工况最差 MAE 不高于 8%时，程序才会冻结候选模型并执行一次 A123#5 跨电芯评估。A123#5 不参与训练、归一化、早停、学习率调度或候选选择。

```powershell
# 缩小样本和轮次，先验证完整流程
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage smoke

# 正式完成内部五种子与留一工况验证
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage internal

# 仅在内部验收通过后训练候选并评估 A123#5
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage cross-cell

# 自动执行 internal，并在通过时继续 cross-cell
..\..\work\soc_venv\Scripts\python.exe -m src.evaluation.generalization_experiments --stage all
```

所有产物保存在数据中心的 `03_模型与实验结果\03_综合泛化验证`，不会覆盖原基线。程序支持跳过已经验证完整的成功任务，并保留失败日志以便继续运行。
