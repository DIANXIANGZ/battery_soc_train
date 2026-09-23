# SOC PyTorch 线性基线正式训练归档

- 状态：`SOC_PYTORCH_LINEAR_FORMAL_PASS_SCOPED`
- 日期：2026-09-22
- 独立验收：新测试工程师已明确给出 `FORMAL TRAINING PASS`。
- 适用范围：仅 `LGHG2_001` 这一已见物理电芯的六种完整工况留出结果；不代表未知电芯泛化，也不宣称跨来源泛化。

## 执行与模型

- 唯一训练命令：`PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3.12 -u .superpowers/sdd/2026-09-22-soc-pytorch-linear/soc_pytorch_linear_train.py --formal-authorized`
- 退出码：`0`；运行状态：`SOC_PYTORCH_LINEAR_FORMAL_COMPLETE`。
- 环境：Python 3.12.13、PyTorch 2.13.0、NumPy 2.5.1、scikit-learn 1.9.0；CPU，无 CUDA。
- 算法：`torch.nn.Linear(4, 1)`，float64、CPU，闭式 Ridge，`alpha=1.0`，拟合截距且不惩罚截距。
- 特征：`time_s`、`voltage_v`、`current_a`、`discharged_ah_prefix`；标签为固定名义 3 Ah 参考下的因果前缀 SOC。
- 预处理：标准化参数仅在每折训练数据上拟合；无验证集、无早停、无随机行切分。
- 留出：6 折完整 condition 留一；每折 5 个 condition 训练、1 个 condition 测试，每个测试 condition 独立且只测试一次。测试预测共 411,135 行，`source_row_index` 唯一，折测试行数合计为 411,135。
- 指标：宏平均 MAE `3.05958233824622e-06`；宏平均 RMSE `3.850856181081782e-06`。
- 模型回载复算：从 `models.pt` 重载每折模型后复算全部测试预测；相对于 `predictions.csv` 的最大绝对差为 `0.0`，各折及宏指标复算一致。

## 版本与实现绑定

- 数据版本：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/soc-lightweight-condition-v1-2026-08-27/soc-baseline-v1`
- 数据来源：`mendeley-b5mj79w5w9-v1`；物理电芯：`LGHG2_001`；样本数：411,135。
- READY：`af174d4890b00ddc117cbac65c5f469613f286c3303ed274dcdf06b15629d7c6`
- manifest：`fc5c900fd8377699df05f0344a2a70d9bf10ed90fe5b10b49fff5d9436346289`
- samples.csv：`78dc6896c6ba7c98622002a3e72307b48aa809e801b5fc2439ada5950e59a5ec`
- source_files.csv：`e51db9747c91161dc1bceec2d95c8cc7b81f54e63110122e1b7a30dd11851e03`
- Runner `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/.superpowers/sdd/2026-09-22-soc-pytorch-linear/soc_pytorch_linear_train.py`：`0b76356d804d4257fd423c5efafc0dfb249ce0d3b9082f34e0551864d77f79d0`
- 训练配置 `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/configs/training/non_rul_baseline/soc-pytorch-linear-formal.json`：`cb1c3cb72d3be2d8e694c0109576751e7f1e5dde7b3ecd8cf463538220aab501`
- 基础 SOC 配置 `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project/configs/training/non_rul_baseline/soc.json`：`cbd5031ee08186c10b314d09e9f03641f6b642ad7233d4fec07e30a2216ea166`

## 正式结果工件

结果目录：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/07_SOC轻量基线/soc-lightweight-condition-v1-2026-08-27/pytorch-linear-formal-v1`

结果目录仅含以下五个工件。四个 payload 工件的大小与 SHA-256 与 `run_manifest.json` 相互核对；`run_manifest.json` 自身大小与指纹另经独立核验并列于下表：

| 工件 | 字节数 | SHA-256 |
|---|---:|---|
| `models.pt` | 8,155 | `e28138d9eaa8c3f2845a2bb5a59cbfe2b8a1652b969f2e264a1f7c3720196567` |
| `fold_metrics.json` | 2,619 | `0493b8ca90831309b96aea284e2f9a446c3e1a153ef06113c69811c51ac3209f` |
| `predictions.csv` | 73,265,696 | `2c507f79e45059469465afcbda95a94020a35da130fd9e2a1a2ace370ba56e94` |
| `training.log` | 1,108 | `c5d7cdd216595da712249c2febd567f3a51048652706a689d25975851b1b1403` |
| `run_manifest.json` | 4,944 | `68c2a2e4bbab37a60a6c95fb55ad4d8c8b517f87991e7fd00f0ad01928dbdf7b` |

## 安全与范围声明

- 本次只使用上述 SOC READY 版本；未读取或混入其他目标、RUL 或冻结资产。
- 未修改数据版本；未导入或运行 XGBoost；未执行 Git 操作。
- 本归档仅确认这一固定配置和已见单电芯六工况留出实验的正式训练结果，不扩大为未知电芯泛化结论。
- 训练结果的独立验收状态为 PASS；本归档本身仅汇总既有运行和回读证据，不启动训练或更改结果。
