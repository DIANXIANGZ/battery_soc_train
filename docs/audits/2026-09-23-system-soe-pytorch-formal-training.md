# 系统级 SOE PyTorch 正式训练归档

## 结论

本次系统级 SOE PyTorch 线性基线已完成正式训练，并通过独立测试验收。

- 状态：`FORMAL TRAINING PASS`
- 目标：`system_soe`
- 适用范围：社区储能系统级数据，不代表单电芯或未知电芯泛化能力
- 标签：`soe_source_value`
- 标签单位：来源未明确，记录为 `unspecified_source_unit`
- 未启动重复训练，未修改训练数据版本，未执行 Git 操作

## 数据与模型

- 数据版本：`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/system_soe-baseline-v1`
- 数据来源：Zenodo 8381142，版本 1.0
- 训练数据：21,205 行，238 个 `RequID` 组
- 测试数据：4,933 行，60 个 `RequID` 组
- 训练组与测试组：零重叠
- 输入：当前行 `SoC`、`Ptcb`、`Ptei`
- 模型：CPU `torch.nn.Linear(3,1)`，`float64`
- 标准化：仅使用训练组计算均值和标准差
- 验证集：无
- 提前停止：无

## 训练结果

- 平均绝对误差：`13.538709044079217`
- 均方根误差：`16.552627288336616`
- 模型保存后重载预测最大差：`0.0`
- 预测文件：4,933 行，覆盖全部 60 个测试组，数值全部有效

结果目录：

`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/08_系统SOE轻量基线/system_soe-baseline-v1/pytorch-linear-formal-v1`

## 固定输入指纹

- `READY.json`：`c18455709c3c7977e2c81ebcca95bf4d4de427f117d820a5f515fe44d2c6d6cf`
- `manifest.json`：`72c4cb27e018c8e6fc592fe924ef79316dd29b175a6f51c6d06bf39dc4570a90`
- `samples.csv`：`d6abe22b5b3040bb39977263bfb40f1e2e77106f6e9ab7e600784513ee0b0e8e`
- `source_files.csv`：`8e4ef51edcf3e74d1ab5cd2bc77a734b14335dd31b04f192a64995e3f35b1601`
- 固定训练配置：`a8892c2cf159e88c2d2c9c6cf6ff45bb822eb84f24515234d7cc01443cf72e63`
- 训练入口：`dda74e90c9a06e099d15b84d1b5302b44f42e07852d51da2c52171fa04c572ab`

## 结果工件指纹

- `metrics.json`：`58b112ddce207cd763d83ab3a91608326789b88515e1bcdd5d16e44d1dff8f7a`
- `model_state.pt`：`06a56abff7ab3a0694f3216ec248614bfba5a57daaabcd0e70fea4b659f5403f`
- `predictions.csv`：`b9e4cc9f1a11b6f52b7ce11301e7e831e7fe8e0f3b7e02efa346f0c8d0c4fdb7`
- `run_manifest.json`：`693091d3f3b3a4683ed1089f219ea53eefdbbadbfe73746a8c2c29c5247d7ff9`
- `training.log`：`4c9108e08f0a33934fc830eac34550d2da2ee4250306e0adb80642073cfcf3be`

## 验证记录

- 训练入口专项测试：7 项通过
- 系统级 SOE 适配、数据版本、训练入口和版本构建联合回归：125 项通过
- 语法检查：通过
- 烟雾测试：通过
- 正式训练：退出码 0
- 独立测试：回读模型、预测、组隔离、指标和全部工件指纹后判定通过

## 边界

本结果只说明固定来源、固定数据划分下的系统级 SOE 线性基线可运行且结果可复核。由于来源没有明确给出 SOE 字段单位，本报告不把误差解释为百分比、kWh 或其他物理单位。
