# Phase 2 详细实施计划：Reviewer Agent（审查引擎）

> 对应 [VISION.md](VISION.md) 第七节 Phase 2，此前因为 Phase UI 提前执行而顺延
> 前置条件：[PHASE0.md](PHASE0.md)、[PHASE1.md](PHASE1.md) 已完成——单标的与截面两条路径都能产出完整 artifact 和指标；[PHASE_UI.md](PHASE_UI.md) 的核心三件套已经能展示这些 artifact
> 目标：VISION.md 称 Reviewer 为"产品灵魂"——现在 Coordinator 产出的每一个结果都只有 Sharpe/IC 这类"看起来漂亮"的数字，没有任何自动化的质疑。Phase 2 要把 VISION 第五节列的审查清单从文档变成会自动运行、有测试锁定的代码。

---

## 一、为什么现在做，以及和"模型写什么代码写什么"准则的关系

1. 当前系统的结构性风险：一个过拟合、依赖未来函数、或者只在两周牛市里赚钱的因子，和一个真正稳健的因子，在现在的 research_note.md 里长得一模一样——都是一张漂亮的净值曲线和几个指标。这正是 VISION.md 里反复强调、Claude Science 也反复强调的问题：**结果好看不等于结果可信**。
2. VISION.md 第十一节定的准则在 Phase 2 上最吃紧："审查逻辑本身（怎么检测未来函数、怎么算手续费敏感性）应该是'代码写'的部分，Reviewer Agent 只是调用这些检查工具并解读结果，不应该让模型自己现场发明这套逻辑"。Phase 2 的每一个检查项都必须是**确定性、可单测、阈值集中管理**的 Python 函数，不是让 LLM"你觉得这个因子稳不稳"。
3. Phase 0/1 已经用 `sanity_check_metrics` 开了一个小口子（Sharpe/收益率超出合理范围就强制警告，且这个警告是自动触发、不经过模型判断的）。Phase 2 本质上是把这个模式系统化、扩展到 VISION 第五节列的全部审查项。

---

## 二、验收标准（先定终点）

**验收命令（复用 Phase 0 / Phase 1 已经验收过的两条路径，这次要求两条路径都自动带审查）：**

```
$ python -m quantbench "测试20日动量因子在AAPL上的表现，2018-01-01到2024-01-01"
$ python -m quantbench "在标普500成分股里测试20日动量因子的截面表现，2022-01-01 到 2024-12-31，等权十分位多空组合"
```

系统必须在 backtest 成功后自动完成（不需要用户额外要求、不经过模型是否调用的判断）：

1. 未来函数静态检测（对生成的 `compute()` 源码做 AST 扫描）
2. 样本内/样本外切分复跑，对比 Sharpe/IC 衰减
3. 手续费敏感性扫描（1x / 1.5x / 2x 假设成本下重算）
4. 参数稳定性扰动（对代码里的数值字面量做 ±20% 扰动，复跑对比）
5. Regime 依赖检查（按年份切分收益贡献）
6. 极端交易依赖检查（剔除表现最好的 5% 交易日后复算）
7. 换手率现实性检查（复用已有的 `turnover_annual` 指标做阈值判断）
8. Beta 暴露检查（对 benchmark 做线性回归）
9. （仅截面场景）标的池偏差检查：多空组合收益是否集中在少数标的
10. 把以上全部结果汇总成一个确定性规则算出的 verdict（`STRONG` / `PROMISING` / `WEAK` / `REJECTED`），連同每一条 finding 写入 `review_report.json` + 追加进 `research_note.md`
11. Coordinator 的最终自然语言回答必须原样陈述 verdict 和其中的 CRITICAL/WARNING 发现，不能省略或淡化（沿用现有对 `warnings` 的强约束模式）

**验收标准的两个具体测试场景（直接取自 VISION.md 第七节对 Phase 2 的验收描述）：**

- 故意写一个包含未来函数的因子（比如 `df["close"].shift(-1)` 直接作为信号），Reviewer 必须检测到，verdict 必须是 `REJECTED`。
- 用一个明显过拟合的因子（核心参数 ±20% 就让 Sharpe 大幅波动、且样本外相对样本内显著衰减），Reviewer 必须打出 `WEAK` 或更差，并且给出具体原因（不能只说"不太好"）。

**Definition of Done：** 两条验收命令跑完后，`runs/<run_id>/` 目录里出现 `review_report.json`（结构化，UI/未来的实验库可以直接消费）和 `research_note.md` 里新增的审查区块；Phase 0/1 已有的两个验收场景（正常的动量因子）重新跑一遍，不应该被误判成 `REJECTED`（即 Reviewer 不能把"正常但普通"的结果错误地打成"致命问题"）。

---

## 三、明确不做的事（Phase 2 边界）

| 不做 | 留到哪个 Phase / 原因 |
|---|---|
| 独立的第二次 LLM 调用来"写"审查叙述（真正的 Actor-Critic 双 agent） | v1 的 verdict 和 finding 全部是确定性代码产出，足够满足"结果可信"的核心诉求；Coordinator 现有的最终回答负责把这些结果转述给用户。真正独立的 Reviewer LLM persona（比如更丰富的"下一步实验建议"）作为后续迭代 |
| 新增可视化图表（手续费敏感性曲线、参数热力图） | VISION 5.4 列了这些图表类型，但本阶段先把审查逻辑和判断做对；图表复用现有 equity curve / group returns / IC 图，新图表留给 Phase UI 的下一轮打磨 |
| 跨多个 run 的审查结果比较（"这一批因子里哪个最稳健"） | Phase 3 实验管理，需要先有 Experiment Library 才能做跨 run 检索 |
| 用户可配置的审查阈值（比如自己设定"OOS 衰减多少算警告"） | 先用代码里集中管理的常量（类似现有 `SANITY_SHARPE_LIMIT`），等有真实使用反馈再考虑开放配置，避免过早暴露一堆不知道怎么调的旋钮 |
| 真正理解代码语义的参数扰动（模型显式声明 `parameters: dict`，而不是随便扰动数值字面量） | 需要改 `compute(df)` 的调用接口，让模型额外声明参数字典，这是更大的接口改动；本阶段先用对数值字面量做 AST 扰动的启发式方案，已知有误伤/漏报 |
| Docker / 进程级沙箱执行隔离 | Reviewer 只是更多次调用已有的 `run_signal_code` / 回测引擎，不改变 Phase 0 定的 builtins 白名单隔离级别 |
| A股/期货等新资产类别的 benchmark 处理 | Beta 暴露检查先只覆盖当前已支持的美股（benchmark=SPY）和 crypto（benchmark=BTC/USDT）两种 |

**红线不变：任何功能想加进来，先问"验收标准需要它吗"。**

---

## 四、项目结构变化

```
quantbench/
├── review/                          # 新增：Reviewer 的全部确定性检查引擎
│   ├── __init__.py
│   ├── lookahead.py                 # 未来函数静态检测（AST）
│   ├── out_of_sample.py             # 训练/测试切分 + 复跑对比
│   ├── cost_sensitivity.py          # 手续费敏感性扫描
│   ├── parameter_stability.py       # 数值字面量扰动 + 复跑对比
│   ├── regime.py                    # 按年份切分收益贡献
│   ├── tail_dependence.py           # 剔除极端交易日后复算
│   ├── beta_exposure.py             # 对 benchmark 做线性回归
│   ├── symbol_concentration.py      # 仅截面场景：标的池偏差
│   └── report.py                    # ReviewFinding / ReviewReport / verdict 规则 / markdown 渲染
├── engine/
│   └── metrics.py                    # 扩展：新增 review 用到的通用小工具（如线性回归 beta/R²）
├── agent/
│   ├── coordinator.py                # 扩展：backtest 成功后自动调用 run_review()，不经过模型选择
│   └── prompts.py                    # 扩展：教模型必须原样陈述 verdict 和 CRITICAL/WARNING 发现
└── skills/
    └── report.py                     # 扩展：research note 模板加入"Reviewer 审查报告"区块
```

**关键设计决定：Reviewer 不是一个模型可以选择调不调的工具。** 现有的 `fetch_ohlcv` / `run_signal_backtest` / `build_universe` / `run_cross_sectional_backtest` 是 LLM 决定何时调用的工具；Reviewer 不一样——如果做成工具，模型有可能在觉得"结果已经很好了"的时候跳过审查，这正是 Reviewer 存在的意义要防止的事。所以 `run_review(...)` 直接挂在 `_run_signal_backtest` / `_run_cross_sectional_backtest` 内部（和现在的 `sanity_check_metrics` 同一个位置），backtest 一成功就无条件执行，结果作为工具返回值的一部分塞给模型，模型只能"转述"，不能"跳过"。

---

## 五、核心模块设计

### 5.1 `review/lookahead.py` —— 未来函数静态检测

对模型生成的 `compute(df)` 源码做 AST 扫描，找**已知的**未来函数模式。这是启发式检测，不是形式化证明（真正判定"有没有用未来数据"在通用情况下是不可判定的），所以要保守：宁可漏报也不能高误报率，否则 Reviewer 的可信度会被自己拖垮。

```python
@dataclass(frozen=True)
class LookaheadIssue:
    pattern: str        # e.g. "negative_shift", "unwindowed_full_column_aggregate"
    detail: str          # 人类可读描述，包含出问题的代码片段
    line: int | None


# 检测规则（按置信度从高到低）：
# 1. 负数 shift/diff/pct_change：df["close"].shift(-1) / .diff(-1) / .pct_change(-1)
#    —— 高置信度，这就是最经典的未来函数写法。
# 2. 对整列做全局聚合后原样用作逐行特征，且聚合前没有 .rolling(...)/.expanding(...)：
#    例如 df["close"].mean() 被直接赋给一个会逐行使用的变量
#    —— 中等置信度，是新手最常踩的隐蔽未来函数，但存在合理的例外（比如给整段
#    数据打标准化用的全局统计，如果模型确实想这么干，这属于"用全部历史给自己开卦"，
#    仍然应该被标记，不算误报）。
# 3. 反向索引/切片：df[::-1]、np.roll(..., shift<0)、df.iloc[i+1] 这类显式访问未来行
#    —— 高置信度。
# 4. 用 df 末尾的值（如 df["close"].iloc[-1]）作为对每一行都相同的特征
#    —— 高置信度，等价于"提前知道整段数据的最后收盘价"。


def detect_lookahead(code: str) -> list[LookaheadIssue]:
    """Parse `code` with `ast`, walk the compute() function body, match
    against the rule set above. Never executes the code - pure static analysis.
    """
```

**为什么用 AST 而不是正则：** 正则会被字符串/注释里的相似文本、变量名巧合坑（Phase 0 已经因为这类脆弱匹配吃过教训）。AST 能准确定位"这是不是真的在调用 `.shift()`，参数是不是真的是负数字面量"，而不是文本上像。

### 5.2 `review/out_of_sample.py` —— 样本外衰减检查

复用已经拿到的价格数据（不重新拉取），按时间切成 train/test 两段，分别重跑一遍已有的回测引擎，对比 Sharpe。

```python
@dataclass
class OOSResult:
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    sharpe_decay_ratio: float | None   # test_sharpe / train_sharpe，符号翻转时为 None


def split_out_of_sample(
    price_or_panel: pd.DataFrame, split_ratio: float = 0.7
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按时间戳切分，不按行数切分（截面场景下每个时间戳有多行）。"""


def run_out_of_sample_check(
    data: pd.DataFrame,
    compute_factor: Callable[[pd.DataFrame], pd.Series],
    backtest_fn: Callable[..., Any],   # run_vectorized_backtest 或 run_cross_sectional_backtest 的部分应用
    cost_bps: float,
) -> OOSResult:
    """在 train/test 两段上分别重新计算因子、重新跑回测（不是把已有的收益序列切开
    复用 —— 必须重新调用 compute()，否则 test 段会偷偷用到 train 段才有的 warmup 信息，
    等于自己给自己开小灶）。
    """
```

**已知限制（写进文档，不假装没有）：** 用到长 warmup 期（比如 200 日均线）的因子，在只有 test 段数据的情况下前 200 行会是 NaN/不完整，可能让 test 段的样本量显著变小。v1 不解决这个问题（真正的解法是保留 train 段末尾一截作为 test 段的 warmup 缓冲，属于可以在后续迭代加的优化），只是在 `OOSResult` 里带上 test 段实际有效观测数，方便判断"衰减是真衰减还是样本太小"。

**判定规则（`review/report.py` 里集中管理，不散落在各个 check 模块）：**
- `test_sharpe` 和 `train_sharpe` 符号相反且 `train_sharpe` 明显为正 → CRITICAL："样本外表现方向性翻转"
- `sharpe_decay_ratio < 0.5` → CRITICAL："样本外 Sharpe 衰减超过一半"
- `0.5 <= sharpe_decay_ratio < 0.8` → WARNING："样本外表现有衰减"
- 否则 → PASS

### 5.3 `review/cost_sensitivity.py` —— 手续费敏感性

单标的场景可以直接复用已经算出的 `signal`/`position`，不需要重新跑 `compute()`——只需要用不同的 `cost_bps` 重新跑一遍已有的回测数学（`run_vectorized_backtest` 接受现成的 `signal`，本来就很便宜）。截面场景因为 `run_cross_sectional_backtest` 目前把"算因子"和"算组合收益"耦合在一个函数里，v1 先接受重复计算因子的开销（因子计算是纯 pandas 操作，不涉及 LLM 调用，几百个标的量级下仍然是秒级）。

```python
COST_MULTIPLIERS = (1.0, 1.5, 2.0)

@dataclass
class CostSensitivityResult:
    sharpe_by_multiplier: dict[float, float]

    @property
    def unprofitable_at_2x(self) -> bool:
        return self.sharpe_by_multiplier.get(2.0, 0.0) <= 0


def run_cost_sensitivity_check(rerun_at_cost: Callable[[float], dict[str, float]]) -> CostSensitivityResult:
    """`rerun_at_cost(cost_bps)` 是调用方传入的一个闭包，屏蔽单标的/截面两条路径
    在"怎么用新的 cost_bps 重跑"这件事上的差异。"""
```

**判定规则：**
- 2x 假设成本下 Sharpe ≤ 0 → WARNING："在 2 倍假设手续费下不再盈利"
- 1.5x 假设成本下 Sharpe 相对 1x 下降超过 50% → WARNING："对手续费假设敏感"
- 否则 → PASS

### 5.4 `review/parameter_stability.py` —— 参数稳定性

对代码里的数值字面量做 AST 定位和替换（不是正则字符串替换，避免误伤字符串/注释里长得像数字的内容），生成 `±20%` 的扰动版本，复跑对比 Sharpe。

```python
@dataclass
class LiteralSite:
    value: float
    node: ast.AST
    lineno: int


def find_perturbable_literals(code: str) -> list[LiteralSite]:
    """只收集绝对值 >= 2 的数值字面量 —— 排除 0/1/-1 这类几乎总是结构性常量
    （比如 `shift(1)`、`pct_change()` 内部用的符号翻转、布尔判断阈值），
    减少把"不是真正意义上的参数"当成参数去扰动的误报。这是已知的启发式局限，
    在文档里明确写出来，不假装能精确识别"语义上的参数"。
    """


def perturb_code(code: str, factor: float) -> str:
    """用 ast 替换收集到的每个字面量节点为 value * factor（整数字面量四舍五入取整），
    再用 ast.unparse 生成新代码。"""


@dataclass
class ParameterStabilityResult:
    sharpe_by_perturbation: dict[str, float]  # "-20%" / "base" / "+20%" -> sharpe
    sharpe_spread: float

    @property
    def unstable(self) -> bool:
        return self.sharpe_spread > PARAMETER_INSTABILITY_THRESHOLD


def run_parameter_stability_check(
    code: str, rerun_with_code: Callable[[str], dict[str, float] | None]
) -> ParameterStabilityResult | None:
    """rerun_with_code 对扰动后的代码执行失败（比如扰动后语义上不再合法，例如窗口
    变成 0）时返回 None，该扰动点直接跳过而不是让整个 run 崩溃 —— 参数扰动允许
    产出'部分结果'，因为扰动生成的代码本身就不保证语义合法。若没有任何可扰动的
    字面量（比如因子代码根本没有参数），返回 None 并在报告里注明"无可测参数"。
    """
```

**判定规则：** `sharpe_spread`（扰动版本间 Sharpe 最大值减最小值）超过阈值（初始设 `1.0`，Day 10 用真实 run 调）→ WARNING："对参数取值敏感，可能过拟合到具体参数"。

### 5.5 `review/regime.py` —— Regime 依赖

```python
def yearly_return_contribution(returns: pd.Series) -> dict[int, float]:
    """按日历年切分净收益序列，每年对总累计收益的贡献占比（用对数收益求和更适合
    可加性，避免复利下"贡献占比加起来不等于100%"的观感问题，报告里同时展示原始
    百分比并注明口径）。"""


def check_regime_concentration(returns: pd.Series, threshold: float = 0.7) -> ReviewFinding:
    """若样本覆盖不足 2 个完整年份，直接返回 INFO"数据覆盖不足以评估 regime 依赖"，
    不勉强给出误导性的 WARNING/PASS。"""
```

**判定规则：** 单一年份贡献超过 `threshold`（默认 70%）的累计收益 → WARNING："收益集中在单一年份/市场状态"。

### 5.6 `review/tail_dependence.py` —— 极端交易依赖

```python
def check_tail_dependence(returns: pd.Series, drop_frac: float = 0.05) -> ReviewFinding:
    """剔除表现最好的 drop_frac（默认 5%）单期收益，重新计算累计收益。如果剔除后
    策略从盈利变成不再盈利（累计收益 <= 0），说明整体盈利依赖极少数交易日。"""
```

**判定规则：** 剔除最佳 5% 交易日后累计收益 ≤ 0 → WARNING："盈利高度依赖少数极端交易日"。

### 5.7 `review/beta_exposure.py` —— Beta 暴露

需要一条 benchmark 收益序列，对齐到策略收益的时间戳上做简单线性回归（不引入额外依赖，用 `numpy.polyfit` 或最小二乘手写即可，不需要 `statsmodels`）。

```python
BENCHMARK_BY_ASSET_CLASS = {"equity": "SPY", "crypto": "BTC/USDT"}


def fetch_benchmark_returns(asset_class: str, timeframe: str, start: str, end: str) -> pd.Series:
    """复用 Phase 0 的 fetch_ohlcv，取 close.pct_change()。fetch 失败（限流/网络问题）
    时不应该让整个 review 失败 —— 上层 catch 住，返回一个 SKIPPED finding 而不是异常。"""


def compute_beta(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> tuple[float, float]:
    """返回 (beta, r_squared)，对齐索引、丢弃缺失后做回归；观测数 < 30 时视为
    数据不足，调用方应该返回 INFO 而不是 WARNING/PASS。"""


def check_beta_exposure(beta: float, r_squared: float) -> ReviewFinding: ...
```

**判定规则：** `r_squared > 0.5` 且 `abs(beta) > 0.7` → WARNING："收益大部分可以用 beta 暴露解释，alpha 不确定"。

### 5.8 `review/symbol_concentration.py` —— 标的池偏差（仅截面场景）

```python
def check_symbol_concentration(weighted_panel: pd.DataFrame, top_n: int = 5, threshold: float = 0.5) -> ReviewFinding:
    """weighted_panel 来自 run_cross_sectional_backtest 内部已经算出的多空组合持仓
    （见 quantbench/engine/cross_sectional_backtest.py 的 _portfolio_weights），
    按标的汇总对总盈亏的贡献绝对值占比，取 top_n 标的合计占比。"""
```

**判定规则：** top 5 标的合计贡献超过 50% 的总盈亏（绝对值口径）→ WARNING："多空组合收益集中在少数标的，不能代表整个 universe"。

### 5.9 `review/report.py` —— 汇总与 verdict

这是把 5.1-5.8 的输出粘起来、给出**唯一、确定性**判定的地方——verdict 计算规则本身也是"代码写"的一部分，不允许模型对同一组 finding 给出不同的 verdict。

```python
SEVERITY_ORDER = ("critical", "warning", "info", "pass")


@dataclass
class ReviewFinding:
    check: str        # "lookahead" | "out_of_sample" | "cost_sensitivity" | ...
    severity: str      # "critical" | "warning" | "info" | "pass"
    message: str
    detail: dict[str, Any]


@dataclass
class ReviewReport:
    findings: list[ReviewFinding]
    verdict: str            # "STRONG" | "PROMISING" | "WEAK" | "REJECTED"
    verdict_reason: str

    def to_dict(self) -> dict: ...
    def to_markdown(self) -> str:
        """渲染格式直接对应 VISION.md 5.2 的示例：### 🔴 CRITICAL ISSUES /
        ### 🟡 WARNINGS / ### ✅ PASSED / ### VERDICT。"""


def determine_verdict(findings: list[ReviewFinding]) -> tuple[str, str]:
    """
    - 任意一条 severity == "critical" -> "REJECTED"
    - 否则 warning 数量 >= 3 -> "WEAK"
    - 否则 warning 数量 in {1, 2} -> "PROMISING"
    - 否则（全 pass/info） -> "STRONG"
    这几个数字（3 档分界线）是 v1 的起点，Day 10 会用真实 run 结果回顾调整，
    调整只改这一个函数里的常量，不改各个 check 模块。
    """


def run_review(
    *,
    code: str,
    returns: pd.Series,
    cost_bps: float,
    rerun_at_cost: Callable[[float], dict[str, float]],
    rerun_with_code: Callable[[str], dict[str, float] | None],
    out_of_sample_data: pd.DataFrame,
    compute_factor: Callable[[pd.DataFrame], pd.Series],
    backtest_fn: Callable[..., Any],
    benchmark_returns: pd.Series | None,
    weighted_panel: pd.DataFrame | None = None,   # 仅截面场景传入，用于标的池偏差检查
    turnover_annual: float | None = None,
) -> ReviewReport:
    """编排入口：依次跑 5.1-5.8 的检查，捕获每个检查内部可能出现的异常（比如
    benchmark fetch 失败），把异常转成一条 severity="info"/"skipped" 的 finding
    而不是让整个 review 中断 —— 审查本身出错不应该拖垮已经跑成功的 backtest。
    最后调用 determine_verdict 汇总。"""
```

### 5.10 Coordinator 集成

```python
# quantbench/agent/coordinator.py，在 _run_signal_backtest / _run_cross_sectional_backtest
# 内部，backtest 成功、ctx.last_metrics 写入之后：

review_report = run_review(
    code=code,
    returns=backtest.returns,
    cost_bps=cost_bps,
    rerun_at_cost=lambda bps: run_vectorized_backtest(ctx.data_df, signal, cost_bps=bps).metrics,
    rerun_with_code=lambda perturbed_code: _safe_rerun(perturbed_code, ctx.data_df, cost_bps),
    out_of_sample_data=ctx.data_df,
    compute_factor=load_signal_function(code),
    backtest_fn=lambda df, factor: run_vectorized_backtest(df, run_signal_code_from_factor(factor, df), cost_bps),
    benchmark_returns=_fetch_benchmark_safely("equity", ...),
)
run.save_json("review_report.json", review_report.to_dict())
ctx.review_report = review_report
if review_report.verdict in ("REJECTED", "WEAK"):
    ctx.warnings.append(f"Reviewer verdict: {review_report.verdict} - {review_report.verdict_reason}")

return {**backtest.metrics, "warnings": new_warnings, "review": review_report.to_dict()}
```

截面场景同理，额外传入 `weighted_panel` 触发标的池偏差检查。`research_note.md` 的两个模板函数（`build_research_note` / `build_cross_sectional_research_note`）各自新增一段：

```
## Reviewer 审查报告
{review_report.to_markdown()}
```

`prompts.py` 的 `SYSTEM_PROMPT` 新增一条强约束（和现有"不能省略/淡化 warnings"同级别）：

```
- Tool results now include a `review` field with a deterministic verdict
  (STRONG/PROMISING/WEAK/REJECTED) and a list of findings. State the verdict
  explicitly in your final answer, and list every CRITICAL and WARNING finding
  verbatim - never omit them, never soften a REJECTED/WEAK verdict into
  something that sounds more positive.
```

---

## 六、按日拆解（预计 9-10 个工作日）

| Day | 任务 | 产出 |
|---|---|---|
| **Day 1** | `review/lookahead.py`：AST 检测规则 + 单测，包含对 Phase 0/1 已有 fixture 因子代码的**反向回归测试**（确保不误报） | 故意注入 `shift(-1)` 的代码被抓到；已知良好因子代码不被误伤 |
| **Day 2** | `review/report.py`：`ReviewFinding`/`ReviewReport`/`determine_verdict`/`to_markdown`，先用手写的假 finding 列表验证渲染格式和判定边界 | verdict 规则的单测覆盖 REJECTED/WEAK/PROMISING/STRONG 四档边界 |
| **Day 3** | `review/out_of_sample.py`：单标的路径打通 + 单测（用合成的"训练期强、测试期随机游走"收益序列验证衰减能被正确识别） | 单标的 OOS 检查可用 |
| **Day 4** | `review/cost_sensitivity.py` + `review/parameter_stability.py`（含 AST 字面量扰动）+ 单测 | 两个检查项独立可用，参数扰动对已知敏感/稳健的两个合成因子给出正确判定 |
| **Day 5** | `review/regime.py` + `review/tail_dependence.py` + 单测（合成"收益集中在单年份"和"收益依赖前 5% 交易日"两类场景） | 两个检查项独立可用 |
| **Day 6** | `review/beta_exposure.py`（含 benchmark fetch，复用 Phase 0 的 `fetch_ohlcv` + 重试）+ `review/symbol_concentration.py`（仅截面）+ 换手率阈值判定 + 单测 | 全部 8 项检查独立可用且都有单测 |
| **Day 7** | Coordinator 集成：`_run_signal_backtest`/`_run_cross_sectional_backtest` 内自动调用 `run_review`，写 `review_report.json`，`RunResult`/`manifest.json` 带上 verdict | 两条验收命令能跑通并产出 review_report.json |
| **Day 8** | `prompts.py` 更新 + `skills/report.py` 两个模板加审查区块 + 端到端测试（含故意未来函数场景、故意过拟合场景） | 验收标准里的两个具体测试场景通过；Coordinator 最终回答不省略 verdict |
| **Day 9** | 回归测试：Phase 0/1 已有验收场景重跑，确认不被误判为 REJECTED；补齐 `test_phase2_reviewer.py` 覆盖率；性能检查（一次 review 的额外耗时应在几秒量级，不应显著拖慢单次 run） | 全量测试通过，`uv run pytest` 干净 |
| **Day 10** | 用真实数据跑几组因子（复用 Phase 1 验收例子：sp500 20日动量），观察 verdict 是否合理，回到 `determine_verdict`/各阈值常量做一轮调整；更新 VISION.md Phase 2 状态、README "已支持能力" | 阈值不再是拍脑袋数字，而是至少见过几个真实 run 的校准结果 |

---

## 七、关键技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| Reviewer 是工具还是自动步骤 | **自动步骤**，不暴露成 LLM 可选调用的 tool | 如果做成工具，模型有可能在"觉得结果已经很好"时跳过审查——这恰恰是 Reviewer 要防止的事；参考现有 `sanity_check_metrics` 的自动触发模式 |
| verdict 由谁计算 | **纯代码**（`determine_verdict`），LLM 只转述 | 直接落实 VISION 第十一节的准则：判断力交给模型的地方仅限于"因子怎么写"，不包括"这个因子算不算过拟合" |
| 未来函数检测方式 | AST 静态分析，不是正则、不是执行时检测 | 正则脆弱、容易被字符串/变量名坑；执行时检测（比如对比扰动输入前后的输出）成本高且不好定位到具体代码行；AST 能精确匹配"真的在调用什么函数、参数是不是字面量" |
| 参数扰动方式 | 对代码里绝对值 ≥ 2 的数值字面量做 AST 替换 | 不需要改 `compute(df)` 的调用接口（不要求模型显式声明 parameters dict），用现有代码就能跑；已知会漏掉"参数是字符串/布尔"和"参数由字面量运算得出"的情况，接受这个 v1 局限 |
| 手续费敏感性怎么复跑 | 单标的复用已算出的 `signal`（不重跑 `compute()`）；截面场景接受重复计算因子的开销 | 单标的路径优化很直接（回测数学本身很便宜）；截面路径的因子计算是纯 pandas、无 LLM 调用，几秒级开销可以接受，避免为了省这点时间去重构 `run_cross_sectional_backtest` 的接口 |
| Benchmark 选择 | 美股用 SPY，crypto 用 BTC/USDT，按当前支持的两种 provider 硬编码 | 和 Phase 1 的 `fetch_ohlcv` provider 路由方式一致（按 symbol 形状分发），Phase 2 不需要引入新的 asset-class 配置系统 |
| verdict 四档阈值 | 先用固定的 3 档 warning 数量分界（`REJECTED`/`WEAK`≥3/`PROMISING`1-2/`STRONG`0），Day 10 用真实 run 校准 | 和 Phase 0 的 `SANITY_SHARPE_LIMIT` 一样先给出"显然不会误伤正常情况"的保守起点，再用真实数据迭代，而不是一开始就假装知道"多少算过拟合"的精确边界 |

---

## 八、风险与应对

| 风险 | 应对 |
|---|---|
| 未来函数检测误报，把正常代码打成 CRITICAL，Reviewer 的可信度被自己拖垮 | Day 1 就把 Phase 0/1 已有的、跑过验收的因子代码做成回归测试集，任何规则改动都要先过这个集合再合入；检测规则按置信度分级，低置信度模式先只出 INFO 不出 CRITICAL |
| 参数字面量扰动误伤"不是参数的数字"（比如百分比换算用的 100），扰动后代码语义错乱导致 Sharpe 剧烈波动，被误判为"参数不稳定" | `find_perturbable_literals` 只收集绝对值 ≥ 2 的字面量；扰动后重跑失败或结果明显不合理（比如触发 `sanity_check_metrics` 的荒谬阈值）时，该扰动点标记为"跳过"而不是计入 spread |
| OOS/参数扰动/regime 等检查在数据量太小（比如用户只测了 3 个月）时统计上没有意义，硬给结论会显得像瞎editorializing | 每个检查都设最低观测数门槛，不满足时返回 `severity="info"`（"数据不足以评估"），不勉强给 WARNING/PASS |
| Beta 暴露检查需要额外拉取 benchmark 数据，可能像 Phase 1 遇到的 yfinance 限流一样失败 | 复用 Phase 1 已经验证过的重试/退避逻辑；fetch 失败时该检查项标记为 `skipped`，不阻塞整个 review 或整个 run |
| 一次 run 里现在要跑好几次回测引擎（OOS ×2、cost ×3、参数 ×2-4），耗时变长，尤其截面场景 | v1 接受这个开销（数据已缓存，重跑的是内存里的 pandas 计算，不是重新拉取网络数据）；Day 9 做耗时基准，如果明显不可接受（比如从秒级变成分钟级），把截面场景的手续费敏感性检查改成复用已算好的 `factor_panel`（拆分 `run_cross_sectional_backtest` 为"算因子"和"算组合"两步）列为紧跟着的优化项，不在 v1 拖慢主线 |
| verdict 四档阈值一开始就是拍脑袋的，容易要么形同虚设（全是 STRONG）要么过于严苛（全是 WEAK） | Day 10 专门留出用真实数据校准的时间；阈值全部集中在 `determine_verdict` 和各 check 模块顶部的具名常量里，方便后续一次性调整，不需要满仓库找散落的魔法数字 |

---

## 九、Phase 2 完成后的检查清单

- [ ] 两条验收命令（单标的、截面）跑通，`runs/<run_id>/review_report.json` 存在且结构完整
- [ ] 故意注入未来函数的因子代码，verdict 被打成 `REJECTED`，`lookahead` finding 指出具体代码模式
- [ ] 一个已知过拟合（参数敏感、OOS 显著衰减）的因子，verdict 被打成 `WEAK` 或更差，且给出具体原因而非笼统评价
- [ ] Phase 0/1 已有验收场景（正常动量因子）重跑，不被误判为 `REJECTED`
- [ ] `research_note.md` 新增"Reviewer 审查报告"区块，格式对应 VISION.md 5.2 的示例（CRITICAL/WARNINGS/PASSED/VERDICT）
- [ ] Coordinator 最终回答里原样出现 verdict 和每一条 CRITICAL/WARNING（`prompts.py` 约束生效）
- [ ] 全部 8 个 review 子模块有独立单测；`test_phase2_reviewer.py` 覆盖 verdict 判定边界和端到端场景
- [ ] `uv run pytest` 全量通过，含 Phase 0/1 已有测试（回归不破坏）
- [ ] 一次 review 的额外耗时在可接受范围内（Day 9 有基准数字，不是凭感觉）
- [ ] 回到 VISION.md，更新 Phase 2 状态；回顾 Phase 3（实验管理）设计是否需要因为 `ReviewReport` 的字段结构做调整（Experiment Library 大概率需要按 verdict 检索/排序）

---

*完成 Phase 2 后，回到 [VISION.md](VISION.md) 更新 Phase 3 计划。Phase 3 的 Experiment Library 将直接消费 Phase 2 产出的 `review_report.json`，让"哪些类型的因子在什么条件下最有希望"这类跨 run 检索问题有确定性的数据基础，而不是靠翻 markdown 文件。*
