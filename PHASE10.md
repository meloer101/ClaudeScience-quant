# Phase 10：Live Signal Monitoring + 策略衰减预警

> 对应 [VISION.md](VISION.md) 第七节 Phase 6"生产化"的前两项：Live signal monitoring、策略衰减预警。团队协作/权限管理明确不做（单用户本地工具，见 VISION.md 第八节）。命名为 PHASE10（而非 PHASE6）是因为 PHASE6.md 已被更早的因子库工作占用（VISION 执行顺序调整导致的编号漂移，见 PHASE6.md 开头说明）。

## 做了什么

Phase 0–9 产出的都是一次性历史区间快照——没有机制在事后用新数据检查一个已判定 STRONG/PROMISING 的因子/组合是否还站得住。本阶段加了一条纯确定性（不调用 LLM/Critic）的检查路径：

1. **增量数据刷新**（[quantbench/data/refresh.py](quantbench/data/refresh.py)）：用重叠窗口重新调用现有 `fetch_ohlcv`/`fetch_universe_ohlcv` 并 `upsert_ohlcv`（本就幂等），不引入新的 provider 能力或存储机制。
2. **衰减判定**（[quantbench/monitor/decay.py](quantbench/monitor/decay.py)）：把一个 run 的历史回测 Sharpe 和"数据截止点之后"的实盘同款代码 Sharpe 做比值，复用 `review/out_of_sample.py` 同款阈值（<0.5 alert、<0.8 watch），观测数不足时诚实返回 `insufficient_data` 而不是编一个数字。
3. **编排管线**（[quantbench/monitor/pipeline.py](quantbench/monitor/pipeline.py)）：`check_run_decay(run_id)` 只处理 verdict ∈ {STRONG, PROMISING} 的 run；分单标的 / 截面 / 组合三条分支重新执行该 run 自己的 `compute()`（或组合的固定权重）；结果写回**同一个 run 目录**的 `monitoring_report.json`（历史列表）+ 补丁 `manifest.json` 的 `live_monitoring` 摘要字段——**不建新子 run，不跑 Critic**（衰减检查是重复性健康检查，不是新研究结论，见下"架构取舍"）。
4. **调度**：无新依赖，纯 stdlib `time.sleep` 轮询循环，`quantbench monitor watch` 前台命令；单次触发用 `quantbench monitor check <run_id...>` / `--all-alive`。
5. **三路入口**：CLI（`monitor check`/`monitor watch`）、API（`GET/POST /api/runs/{id}/monitoring[/check]`，`/api/runs` 列表带 `monitoring_status` 徽章字段）、Coordinator 第 7 个工具 `check_run_decay(run_id)`（对话内可用，同一条确定性管线）。
6. **前端**：`MonitoringStatusBadge`（run 列表行的小圆点）+ `MonitoringPanel`（run 详情页的检查历史表 + "立即检查"按钮）。

## 架构取舍

- **监控不创建新 run、不跑 Critic**，区别于 Phase 9 `optimize_portfolio`（会建子 run + 独立审查）：组合优化产出新研究结论值得溯源；衰减检查是对同一个 run 的高频重复健康检查，每次都建 run 会很快把实验库刷满噪声。
- **调度不引入新依赖**（无 APScheduler/Celery）：单用户本地工具没有理由为定时任务引入额外基础设施；stdlib 轮询循环 + 用户自己接 cron/launchd 已经够用。

## 已知限制（v1 明确不追求的精确度）

`config.yaml` 目前不持久化 timeframe（截面/组合 run）、`n_groups`、`cost_bps` 这几个原始回测参数（本阶段只给单标的 run 新增了 `fetch_params` 持久化）。衰减检查重跑时对这些用文档化的默认值近似（`quantbench/monitor/pipeline.py` 顶部的 `_DEFAULT_TIMEFRAME_BY_ASSET_CLASS`/`_DEFAULT_N_GROUPS`/`DEFAULT_COST_BPS`），而不是原 run 的确切取值。这是有意为之的 v1 简化——补齐这些字段的持久化是后续增量工作，不阻塞衰减监控本身可用。因此：

- 早于本次改动创建的单标的 run（config.yaml 没有 `fetch_params`）无法被监控，`check_run_decay` 会明确返回错误而不是静默猜测符号。
- 截面/组合 run 的重跑用近似参数，其"近期 Sharpe"不是原 run 参数下的精确复现，只是一个诚实的方向性信号。

## 验证

`uv run pytest tests/test_phase6_monitoring.py -q` 覆盖：衰减阈值判定、增量刷新幂等性、单标的/组合两条 `check_run_decay` 端到端分支、verdict 门槛、`run_monitor_pass` 只处理存活 run、CLI、API。全量 `uv run pytest -q`：140 passed（128 原有 + 12 新增），零回归。

手动验证：对一个真实 AAPL 单标的 STRONG run（真实 yfinance 数据）跑 `quantbench monitor check`，确认 `monitoring_report.json`/`manifest.json.live_monitoring` 正确写入；前端 `MonitoringStatusBadge`/`MonitoringPanel` 渲染正确，"立即检查"按钮触发新一轮检查并刷新历史表。
