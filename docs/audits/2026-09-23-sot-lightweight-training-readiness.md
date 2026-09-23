# SOT 轻量基线训练准备审计

本报告只覆盖 Zenodo 13759419 V1 的 `source-native-temperature` 逐条温度估计基线；不代表摄氏度、不代表未知电芯泛化，也不解除 SOE、SOH、RUL 或冻结资产的门禁。

## 数据版本

独立版本根：
`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/02_训练数据/05_非RUL独立候选/sot-lightweight-temperature-v1/sot-baseline-v1`

版本固定四件套：

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| READY.json | 106 | 8125ca375d0c44014b9db221bb7d63d57462df975c3ca219eaa1585a009ba91a |
| manifest.json | 1,651 | 5a772d0e80885719b536f71a9d91278526350432747e5c5d10201344b806ade5 |
| samples.csv | 1,641,792,795 | 12b3441797f972fda1d5ec640a7cd021f8dd4d7576caf02869903d0b67f3a767 |
| source_files.csv | 943 | 2cadbe0752d09a30ccaa72cdbd438ff601fc96ba60d9aafa68effbd673e0f5e4 |

manifest 报告 11,251,581 行，25 个 CSV 成员中 24 个接收、1 个因永久缺温度字段拒绝。五个可证明组中，训练为四组，测试为完整的 `cell_40ah_1|40Ah|2C|100%DOD` 组；validation=null，early_stopping=false。温度标签保持 `source-native-temperature`，特征只使用当前行电压/电流。

## 来源指纹

三个已批准隔离 ZIP 的字节数/SHA-256：

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| Dataset_1_40Ah_battery.zip | 156,521,437 | c86f15757d3ead977a8f3835cd38b1bb3e0b3246769531dbdb9afd771f862056 |
| Dataset_2_280Ah_battery_1.zip | 63,100,445 | 900f69d0d9d5aabf02a50062a5d8aee06255675ae5c7aa891e5d663f708c10be |
| Dataset_3_280Ah_battery_2.zip | 55,766,906 | aca46f0771fc2cc646564ea21447f96ef7f116b800b2fb13c6595f3430293914 |

## 实现与测试

- 适配器：`src/data_processing/non_rul_baseline/sot_lightweight.py`
- PyTorch 入口：`src/training/non_rul_baseline/sot_lightweight_pytorch.py`
- 配置：`configs/training/non_rul_baseline/sot-lightweight-pytorch-linear.json`
- 失败优先用例：`tests/non_rul_baseline/test_sot_lightweight_adapter.py`、`tests/non_rul_baseline/test_sot_lightweight_pytorch_train.py`
- 联合回归：`140 passed in 0.63s`
- compileall：exit 0
- `git diff --check`：exit 0

当前送测文件指纹：

| 文件 | SHA-256 |
|---|---|
| `src/data_processing/non_rul_baseline/sot_lightweight.py` | `5c3ee020e4ab15a000f5a532984e8dcfe38cdf91f862523adb082a7edcb35ea7` |
| `src/training/non_rul_baseline/sot_lightweight_pytorch.py` | `a8426bc477cb2a33b5e84295a8ffee12564e81ff41ceed0aba2ea2a9daa6b0bb` |
| `tests/non_rul_baseline/test_sot_lightweight_adapter.py` | `ca456b6f46bed803831325660daa7f6266a05e629904a640ce8ad14757ef789b` |
| `tests/non_rul_baseline/test_sot_lightweight_pytorch_train.py` | `b3e45f1b2841314ef62d9ce2a51e36686e23bcc582823ef7213afa4987fd2752` |
| `configs/training/non_rul_baseline/sot-lightweight-pytorch-linear.json` | `426caa483aa4e316f77c179faa1aa602b0b0448c894212bc35af222d11845e87` |

正式路径采用流式拟合和流式预测写出，不把完整 `samples.csv` 装入内存。

## 已授权运行结果

环境预检：`/opt/homebrew/bin/python3.12`（Python 3.12.13，numpy 2.5.1，torch 2.13.0）。

Smoke 临时目录：`/private/tmp/sot-lightweight-smoke-20260923`。命令：
`/opt/homebrew/bin/python3.12 -m src.training.non_rul_baseline.sot_lightweight_pytorch --config configs/training/non_rul_baseline/sot-lightweight-pytorch-linear.json --output /private/tmp/sot-lightweight-smoke-20260923 --stage smoke --smoke-authorized --max-rows 1000`
命令 exit 0，500 行训练/500 行测试，MAE 27.500000000000025，RMSE 27.50000000000003；工件回读有限，run_manifest 绑定本版本四个哈希。工件 SHA：

- `metrics.json` `88bdc03f2b88c24ac8b94d52dd50aaf52e4f0f7d4667396d623e0493f91d603e`
- `model_state.pt` `c35327e9a36cb82c77ed791c24519207ca9d34572fa1f8af5f680436224c6c25`
- `predictions.csv` `461c208a6525247bf4e764cecdc455714d49cc54df2eb7271551cb297d70750b`
- `run_manifest.json` `320ed79597aa738c3b3467af0e3a2bfe1b7abd0f152266a7bb7f8a241a8f34ad`
- `training.log` `4dd4ab6a2c589c5d556c6bc49c88ce38dca0fd89efe3d400476943ff66711eae`

正式结果目录：
`/Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/07_SOT轻量基线/sot-lightweight-pytorch-v1/formal`

正式命令：
`/opt/homebrew/bin/python3.12 -m src.training.non_rul_baseline.sot_lightweight_pytorch --config configs/training/non_rul_baseline/sot-lightweight-pytorch-linear.json --output /Users/wanghaoming/Public/SOC电池数据中心/SOC电池数据中心/03_模型与实验结果/07_SOT轻量基线/sot-lightweight-pytorch-v1/formal --stage formal --formal-authorized`
命令 exit 0；训练 9,693,376 行、测试 1,558,205 行，MAE `5.016611990628302`，RMSE `10.040537547113313`。结果目录严格只有五个工件：

- `metrics.json` 270 bytes，`b68e912eea9e018a00e6e6a94ad6bed6ff7050c05b213960518ffc38797f4cbc`
- `model_state.pt` 2,461 bytes，`181c11ed7d13466943e2ea3f4ae3fdc9cada557c32aa48ae31b19e5b3dd20a74`
- `predictions.csv` 188,084,645 bytes，`92aef8e10b77a5e419b5104f06f5dafd0c126d7bb076eaed3daf9ff173b02eb4`
- `run_manifest.json` 1,266 bytes，`448d9b3a9a4489d06ad038f6657b1738e19d0e8809a03dd170f5d3fc7eb135c`
- `training.log` 103 bytes，`ba5dc8ab70eb03dd7e33fe7da01eea7308ac72299a7b38d97404f769ffd2acb9`

独立回读确认正式 predictions 为 1,558,205 行，只有测试组 `cell_40ah_1|40Ah|2C|100%DOD`，所有数值有限，禁用语义命中 0；run_manifest 的配置/版本四文件哈希与实际一致。正式结果不声称摄氏度或未知电芯泛化。

## 当前状态

实现、版本、smoke 和正式训练均已在总工程师本轮授权范围内完成；旧 INVALIDATED 版本未覆盖，未改数据版本，未写 Git。正式结果仍仅限已见电芯/工况的 source-native-temperature 基线，不等价于跨电芯泛化或摄氏度精度结论。
