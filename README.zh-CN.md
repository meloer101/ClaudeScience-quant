<p align="right">
  <a href="README.md">English</a> ｜ <strong>中文</strong>
</p>

<p align="center">
  <img src="docs/assets/banner-workflow.png" alt="QuantBench — 面向量化研究的 AI 工作流" width="900" />
</p>

<h1 align="center">QuantBench</h1>

<p align="center">
  <strong>从想法到经审查的回测，一条命令完成。</strong>
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> &nbsp;·&nbsp;
  <a href="#核心能力">核心能力</a> &nbsp;·&nbsp;
  <a href="#web-工作台">Web 工作台</a> &nbsp;·&nbsp;
  <a href="#命令行用法">命令行用法</a> &nbsp;·&nbsp;
  <a href="#项目结构">项目结构</a> &nbsp;·&nbsp;
  <a href="#路线图">路线图</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/license-AGPL--3.0-green" alt="License: AGPL-3.0" />
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey" alt="Platform: macOS | Linux" />
  <img src="https://img.shields.io/badge/version-0.2.0-orange" alt="Version 0.2.0" />
</p>

---

QuantBench 是一个**本地优先的 AI 量化研究工作台**。用自然语言描述一个策略想法，QuantBench 会把它变成一次可复现、可审计的研究实验——数据拉取、因子代码、回测、质量检查、图表和研究笔记，全部保存到本地 artifact 目录。

它不是自动交易系统，也不是聊天机器人。QuantBench 产出的是**研究产物**——可以复查、复现、交给同事审阅的那种。

<p align="center">
  <img src="docs/assets/hero-landing.png" alt="QuantBench 首页 — 从想法到经审查的回测" width="850" />
</p>

## 快速开始

### 环境要求

| 工具 | 版本 | 安装 |
|------|------|------|
| Python | 3.11+ | [python.org](https://www.python.org/) |
| uv | 最新 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 22+ | [nodejs.org](https://nodejs.org/) |
| LLM API Key | — | 为 LiteLLM 配置 DeepSeek 兼容的 API key |

### 三条命令启动你的第一个实验

```bash
# 1. 安装依赖
uv sync

# 2. 播种示例研究会话（免费，不需要 API key）
uv run python -m quantbench examples seed

# 3. 启动工作台
uv run python -m quantbench serve
```

打开终端打印的 URL。四个预生成的研究会话已经就绪——包含完整的指标、图表、Reviewer 报告和研究笔记。

> 首次启动会自动检测 `uv`/`node`/`npm`，在缺少 `web/node_modules` 时自动执行 `npm install`（约 1 分钟），缺少工具时打印带安装链接的提示。

## 核心能力

### Coordinator Agent

用自然语言描述你要研究什么。Coordinator Agent 理解你的意图，拉取数据，生成因子代码，运行回测，触发质量检查，产出完整的研究产物——无需写模板代码。

```bash
uv run python -m quantbench "在标普500成分股里测试20日动量因子的截面表现，2022-01-01到2024-12-31"
```

### Reviewer 审查引擎

每次运行都会被自动审查。Reviewer 会标记未来函数、过拟合、手续费敏感性、survivorship bias、容量约束等 20+ 项统计和结构性问题。结果附带评定等级：**STRONG**、**PROMISING**、**WEAK** 或 **REJECT**。

### 可复现的研究产物

每次运行的所有内容保存到 `runs/<run_id>/`：

```
config.yaml          # 完整实验配置
signal.py            # 实际运行的因子/信号代码
backtest_result.json  # 指标、bootstrap 置信区间、执行假设
review_report.json   # Reviewer 审查结果和评定
equity_curve.png     # 交互式净值曲线
drawdown.png         # 回撤图
research_note.md     # 自动生成的研究摘要
manifest.json        # 溯源：数据 hash、LLM 用量、注入的 skill
```

### 实验库 & 因子库

按评定等级、资产类别、因子家族或 Sharpe 浏览、筛选和对比历史运行。把经过验证的因子保存到可复用的因子库。从任意运行 fork 出新实验，修改参数的同时保留谱系关系。

### 回测引擎

- **单标的**和**截面**因子回测
- 默认 `open_t+1` 执行价格（现实的，而非乐观的）
- 流动性感知的 spread/参与率上限成本、借贷成本、funding 成本
- 多空贡献分解、beta/市值/行业中性化
- 十分位组合、换手率追踪、参数扰动、regime 分解

### Universe 构建

- **美股**：S&P 500 当前快照和 point-in-time 历史成分
- **加密货币**：通过 CCXT/Binance 获取成交量 Top-N USDT 永续合约
- 通过信任分层显式标注 survivorship/snapshot bias

### MCP & 工作流 Skill

通过 MCP server 和工作流 Skill 扩展 QuantBench——粘贴 `mcpServers` JSON 配置，开关 server，全部热更新无需重启。完全对齐 Claude Code 的 `claude mcp` 体验。

## Web 工作台

基于 React + Vite 的本地工作台，用于浏览运行记录、查看 artifact 和发起新研究。

<p align="center">
  <img src="docs/assets/workbench-run-report.png" alt="QuantBench Web 工作台 — 运行报告与指标图表" width="850" />
</p>

<details>
<summary><strong>更多截图</strong></summary>

<br>

**研究产物** — 每次运行产出可复现的代码、图表和研究笔记：

<p align="center">
  <img src="docs/assets/research-artifacts.png" alt="研究产物：代码、图表和研究笔记" width="850" />
</p>

**自定义面板** — 在 UI 中管理工作流 Skill 和 MCP 连接器：

<p align="center">
  <img src="docs/assets/customize-skills-mcp.png" alt="Skill 和 MCP Server 自定义面板" width="850" />
</p>

**实验库** — 筛选和对比历史研究运行：

<p align="center">
  <img src="docs/assets/experiment-library.png" alt="实验库侧边栏" width="340" />
</p>

</details>

### 交互式图表

零依赖手写 SVG 图表，支持 hover 显示数值：净值曲线、回撤、换手率、十分位收益、成本敏感性、参数扰动、regime 分解、标的集中度和收益相关性矩阵。

## 命令行用法

**发起研究实验：**

```bash
# S&P 500 截面因子回测
uv run python -m quantbench "在标普500成分股里测试20日动量因子的截面表现，2022-01-01到2024-12-31，等权十分位多空组合"

# 加密永续合约截面研究
uv run python -m quantbench "构建 top 30 USDT 永续合约的截面 universe，测试20日动量因子，2023-01-01到2024-12-31"
```

**实验库：**

```bash
uv run python -m quantbench library list --verdict PROMISING,STRONG --sort sharpe
uv run python -m quantbench compare run_A run_B
```

**因子库：**

```bash
uv run python -m quantbench factor save run_A --name momentum_20d
uv run python -m quantbench factor list --family momentum --min-verdict PROMISING
uv run python -m quantbench factor use momentum_20d --param lookback=60 --on "在AAPL上测试，2020-2024"
```

**工作流 Skill：**

```bash
uv run python -m quantbench skill list
uv run python -m quantbench --skill reviewer-weak-triage "我上一个因子被打成 WEAK，帮我看看下一步"
```

**MCP Server：**

```bash
uv run python -m quantbench mcp add-json filesystem '{"command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/data"]}'
uv run python -m quantbench mcp list
uv run python -m quantbench mcp enable fetch
```

## 项目结构

```
quantbench/
  agent/        Coordinator Agent、LLM 封装、提示词
  api/          FastAPI 后端、运行状态管理、artifact 读取
  artifact/     每次运行的归档存储
  data/         数据 provider、universe 构建、缓存、DuckDB warehouse
  engine/       单标的与截面回测引擎、指标计算
  factors/      因子库条目、参数提取、本地 JSON 存储
  library/      实验库索引、筛选、对比、谱系、fork
  review/       Reviewer 审查引擎、评定逻辑、结构化报告
  skilldocs/    工作流 Skill 文档解析、匹配、prompt 注入
  skills/       代码执行、绘图、报告、数据质量等研究技能
skills_docs/    工作流 Skill Markdown 文档
web/            React + Vite 本地工作台
tests/          CLI、API、数据层、回测引擎测试
```

**运行时状态**默认存放在 `~/.quantbench/`（可通过 `QUANTBENCH_HOME` 覆盖）：

```
~/.quantbench/
  data_cache/   下载的行情数据
  runs/         研究运行产物
  factors/      保存的因子库
  literature/   导入的论文
  api_token     本地 API 认证令牌
```

## 本地 API 安全

QuantBench 是**单用户本地研究工具**。API 绑定 `127.0.0.1` 并使用本地令牌（`QUANTBENCH_API_TOKEN` 或 `~/.quantbench/api_token`）。请勿将端口暴露到网络。跨域访问仅限配置的 localhost 来源。

## 路线图

**研究质量** — 扩展 point-in-time universe 覆盖、Reviewer 压力测试和统计护栏校准。

**数据与执行** — 更多资产类别（期货、宏观、另类数据）、数据集版本管理、可选沙箱执行环境、可导出的实验 bundle。

**产品方向** — 标签治理、逐标的 Factor IC Heatmap、多因子 Risk Attribution、多 session 研究工作流。

详见 [CHANGELOG.md](CHANGELOG.md)。

## 风险声明

QuantBench 产出的是**研究产物，不是投资建议**。任何回测都可能受到 survivorship bias、look-ahead bias、数据质量、交易成本假设、过拟合和市场状态变化的影响。所有结果都应该被复核、复现和压力测试后再用于真实决策。

## 许可证

Copyright &copy; 2026 QuantBench contributors.

本项目采用 **GNU Affero General Public License v3.0** 许可——你可以使用、修改和分发本软件，但任何修改版本在分发或作为服务部署时，必须以 AGPL-3.0 许可开源全部源代码。

详见 [LICENSE](LICENSE)。
