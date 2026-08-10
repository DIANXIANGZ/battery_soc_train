# 区间删失 RUL：公式与验收向量备忘录（设计包 A）

**范围：** 仅为 `mendeley_knee_v4_interval_rul` 固定评估合同；不授权训练。阶段 `s∈{soh100_to_80, soh80_to_60}` 完全独立，且每一外层 LOCO fold `f` 的预测 cell 不得参与基线、归一化、校准或任何拟合。

## 1. 输入、输出与适用域

每行标签必须含 `physical_cell_id,stage_id,censoring_type,rul_lower_cycle=L,rul_upper_cycle=U`。有限评分行的 `censoring_type=interval_observed`，且 `L,U` 为整数、`0≤L≤U`；右删失行的 `censoring_type=right_censored`，只含整数下界 `L`，其可行集合为 `[L,+∞)`。`left_censored` 与 `invalid_protocol` 永不进入本评估器。

对每个有限行和名义水平 `α∈A={0.50,0.80,0.90}`，模型须给出闭预测区间 `Pα=[lα,uα]`（实数，`lα≤uα`）。输出 schema 为每个 `(s,f,physical_cell_id,α)` 一行：`n_finite, compatibility_coverage, enclosure_coverage, mean_width, median_width, weighted_interval_score, empirical_enclosure_coverage, right_censored_n, right_censored_lower_bound_violation_rate, baseline_*`；再产生仅对 cell/fold 值作等权平均的 stage 宏平均行。不得以行数加权（微平均）。

嵌套为硬门禁：`l90≤l80≤l50≤u50≤u80≤u90`。任一预测缺失、非有限、端点倒置、非嵌套，或 fold 中无有限观测行时，该 `(s,f)` 的有限指标为 `NOT_COMPARABLE`，全部模型质量门禁 **FAIL**；不得删行或以 0/NaN 替代。

## 2. 固定评分公式（仅有限标签）

令真可行区间 `Y=[L,U]`，预测 `P=[l,u]`：

- 兼容指示量 `C=1[max(L,l)≤min(U,u)]`。
- 包含指示量 `E=1[l≤L 且 U≤u]`。
- 宽度 `W=u-l`。
- 不相交距离 `D=max(L-u, l-U, 0)`。
- 加权区间分数 `WIS=W+2D`（越低越好）。

在一个 cell/fold 的 `n` 行上，coverage 是 `ΣC/n` 或 `ΣE/n`；mean width 和 WIS 是算术均值，median width 为普通中位数（偶数样本取中间两数的算术均值）。**右删失绝不加入这些分母。** 对右删失行仅报 `V=1[u90<L]` 及 `ΣV/n_right_censored`；`u90` 缺失/非有限即 fail-closed，而非自动“覆盖”。

校准固定为**包含校准**：`ECα=mean(Eα)`；`ICE=mean_{α∈A}|ECα-α|`。因此 calibration 的三个水平必须使用同一行的嵌套 50/80/90 区间。模型质量门槛仅在有限行可比时执行：每个 fold **及** stage 宏平均均须 `compatibility_coverage@90≥0.90`、`ICE≤0.10`。

**手算向量（GREEN）：** 两有限行 `Y1=[4,6], Y2=[10,12]`，90% `P1=[3,7], P2=[11,13]`：兼容 `(1,1)`，包含 `(1,0)`，width `(4,2)`，`D=(0,0)`，故 compatibility=`1.00`、enclosure=`0.50`、mean width=`3`、median=`3`、WIS=`3`。对 50/80/90 均令包含率 `(0.5,1.0,1.0)`，则 `ICE=(|.5-.5|+|1-.8|+|1-.9|)/3=.10`。

**手算向量（RED）：** `Y=[4,6]`,`P90=[7,9]`：`C=E=0,W=2,D=1,WIS=4`；若同一行 `P50=[3,8],P80=[4,7],P90=[5,9]`，因 `l90=5>l80=4`，即使逐项可评分也必须整体 FAIL（非嵌套）。右删失 `Y=[8,+∞),P90=[2,7]`：`V=1`，不计入 compatibility/enclosure/WIS。

## 3. 训练折内非训练基线、比较与 fail-closed

对每个 `(s,f)`，仅取训练 cell 的 `interval_observed` 行。令其下端点集合为 `{L_i}`、上端点集合为 `{U_i}`，样本数 `m≥1`。固定 nearest-rank 分位数：`Q_p(x)=x_(max(1,ceil(mp)))`（升序、1-based）。令 `q=(1-α)/2`，基线为常量区间

`Bα=[Q_q({L_i}), Q_(1-q)({U_i})]`。

它不读取测试 cell、测试标签、测试特征或模型输出；按每个阶段和每个 LOCO fold 单独重建。因 `q90≤q80≤q50`，它天然嵌套。基线仅在有限测试行上计算上述 5 类分数；右删失只另报其 baseline lower-bound violation，不与有限评分混合。

“优于基线”是**严格**小于：在每个可比 `(s,f)` **及** stage 宏平均上同时要求 `mean_width_model < mean_width_baseline` 和 `WIS_model < WIS_baseline`。任一相等、NaN、无训练有限行、无测试有限行、任一比较口径不一致，均为 `NOT_COMPARABLE` 并使验收 **FAIL**；不得以另一指标、另一 fold 或宏平均抵消。右删失率只报告，不参与这两个“优于”判定，除非未来版本另行批准比较规则。

**手算向量（GREEN）：** 训练有限标签 `[2,4],[4,6],[8,10],[10,12]`，`α=.50,q=.25`，`B50=[Q.25(L)=2,Q.75(U)=10]=[2,10]`，宽度 8；测试 `Y=[4,6]`。模型 `P50=[3,7]`，宽度/WIS=`4/4`；基线 `8/8`，故该行严格胜出。

**手算向量（RED）：** 同一训练/测试，模型 `P50=[2,10]` 与基线完全相同，宽度和 WIS 均相等，比较结果为 **FAIL（tie）**。若训练折仅有 `right_censored` 行，`m=0`，基线为 `NOT_COMPARABLE`，不得用测试折、全体数据或无穷上界补造基线。
