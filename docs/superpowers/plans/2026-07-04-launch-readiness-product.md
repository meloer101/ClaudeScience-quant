# Launch Readiness Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决 `LAUNCH_READINESS.md`「三、产品角度」列出的首发产品缺口：首次运行体验、示例 run、用户向 README、仓库整理、执行前成本透明、交互面风险声明和发布纪律。

**Architecture:** 产品层先不重构研究内核，围绕“陌生用户 5 分钟看懂价值”补外壳：`quantbench serve` 一键启动本地 API 和 Web，`quantbench examples seed` 创建离线示例 run，README 变成用户路径，内部 phase 文档移到 `docs/dev/`。成本透明通过 preflight estimate 进入 API/CLI/Web 的提交前阶段；风险声明进入 Web 和 factor export。发布纪律用 `CHANGELOG.md`、`docs/RELEASE.md` 和版本检查测试锁住。

**Tech Stack:** Python 3.11+, click, subprocess, ArtifactStore, FastAPI, React/Vite, Vitest, pytest, Markdown docs.

---

## Scope Map

| LAUNCH_READINESS product item | Plan tasks |
|---|---|
| 首次运行体验没有设计 | Task 1, Task 2, Task 3 |
| 需要一键启动 | Task 1 |
| 需要示例 run | Task 2 |
| README from-zero walkthrough | Task 3 |
| 根目录内部文档太多 | Task 4 |
| 单次 run 执行前成本预估缺失 | Task 5 |
| 风险声明未延伸到交互面 | Task 6 |
| 缺 CHANGELOG、tag/release 流程、版本纪律 | Task 7 |

## File Structure

- Modify: `quantbench/cli.py`
  - Add `serve` and `examples seed`; add cost preflight CLI output.
- Create: `quantbench/devserver.py`
  - Start uvicorn and Vite with local-safe env in one command.
- Create: `quantbench/examples.py`
  - Generate deterministic example run directories without LLM or external data.
- Create: `quantbench/agent/cost_estimate.py`
  - Estimate LLM call shape before a run.
- Modify: `quantbench/api/server.py`, `quantbench/api/schemas.py`
  - Add `/api/runs/estimate` endpoint.
- Modify: `web/src/api/client.ts`, `web/src/components/ChatPane.tsx`, `web/src/components/ChatInput.tsx`
  - Show preflight cost estimate before submit.
- Modify: `web/src/components/WarningBanner.tsx`, `web/src/components/ArtifactInspector.tsx`
  - Surface research-risk statement where users inspect or export results.
- Modify: `quantbench/factors/signal_export.py`
  - Include export disclaimer.
- Modify: `README.md`
  - Replace internal-first quick start with from-zero walkthrough.
- Create: `docs/RELEASE.md`
  - Release checklist.
- Create: `CHANGELOG.md`
  - First changelog.
- Move docs:
  - `PHASE*.md`, `GAP_ANALYSIS.md`, `MEMORY*.md`, `VISION.md` to `docs/dev/`
- Tests:
  - `tests/test_serve_cli.py`
  - `tests/test_examples_seed.py`
  - `tests/test_cost_estimate.py`
  - `tests/test_release_docs.py`
  - `web/src/components/ChatInput.test.tsx`
  - `web/src/components/WarningBanner.test.tsx`

## Task 1: Add One-Command Local Startup

**Files:**
- Create: `quantbench/devserver.py`
- Modify: `quantbench/cli.py`
- Modify: `README.md`
- Test: `tests/test_serve_cli.py`

- [ ] **Step 1: Write CLI parser test for `serve`**

Create `tests/test_serve_cli.py`:

```python
from click.testing import CliRunner


def test_serve_dry_run_prints_backend_and_frontend_commands(monkeypatch):
    from quantbench.cli import main

    result = CliRunner().invoke(main, ["serve", "--dry-run", "--api-port", "8010", "--web-port", "5174"])

    assert result.exit_code == 0
    assert "127.0.0.1:8010" in result.output
    assert "5174" in result.output
    assert "QUANTBENCH_API_TOKEN" in result.output
```

Run:

```bash
uv run pytest tests/test_serve_cli.py -q
```

Expected: FAIL because `serve` does not exist.

- [ ] **Step 2: Implement devserver command builder**

Create `quantbench/devserver.py`:

```python
from __future__ import annotations

import os
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServePlan:
    api_command: list[str]
    web_command: list[str]
    env: dict[str, str]
    api_url: str
    web_url: str


def build_serve_plan(api_port: int = 8000, web_port: int = 5173, token: str | None = None) -> ServePlan:
    token = token or os.environ.get("QUANTBENCH_API_TOKEN") or secrets.token_urlsafe(24)
    env = {
        "QUANTBENCH_API_TOKEN": token,
        "VITE_QUANTBENCH_API_TOKEN": token,
        "VITE_QUANTBENCH_API_BASE": f"http://127.0.0.1:{api_port}/api",
    }
    return ServePlan(
        api_command=[
            "uv",
            "run",
            "uvicorn",
            "quantbench.api.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--reload",
            "--reload-dir",
            "quantbench",
        ],
        web_command=["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(web_port)],
        env=env,
        api_url=f"http://127.0.0.1:{api_port}",
        web_url=f"http://127.0.0.1:{web_port}",
    )


def run_serve_plan(plan: ServePlan) -> int:
    env = {**os.environ, **plan.env}
    api = subprocess.Popen(plan.api_command, env=env)
    web = subprocess.Popen(plan.web_command, cwd=Path("web"), env=env)
    try:
        return api.wait() or web.wait()
    finally:
        for process in (api, web):
            if process.poll() is None:
                process.terminate()
```

- [ ] **Step 3: Add CLI route**

In `cli.py`, route before default `_run_request`:

```python
    if args[0] == "serve":
        _serve(args[1:])
        return
```

Add:

```python
def _serve(args: tuple[str, ...]) -> None:
    from quantbench.devserver import build_serve_plan, run_serve_plan

    api_port = int(_option_value(args, "--api-port") or "8000")
    web_port = int(_option_value(args, "--web-port") or "5173")
    plan = build_serve_plan(api_port=api_port, web_port=web_port)
    click.echo(f"API: {plan.api_url}")
    click.echo(f"Web: {plan.web_url}")
    click.echo(f"QUANTBENCH_API_TOKEN={plan.env['QUANTBENCH_API_TOKEN']}")
    click.echo("Backend command: " + " ".join(plan.api_command))
    click.echo("Frontend command: " + " ".join(plan.web_command))
    if "--dry-run" in args:
        return
    raise SystemExit(run_serve_plan(plan))
```

- [ ] **Step 4: Update Web API base handling**

In `web/src/api/client.ts`, support `VITE_QUANTBENCH_API_BASE`:

```ts
const apiBase = (import.meta.env.VITE_QUANTBENCH_API_BASE as string | undefined) ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    headers: jsonHeaders(),
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  return response.json() as Promise<T>;
}
```

- [ ] **Step 5: Update README quick start**

Replace separate API/Web startup as the default path:

````markdown
```bash
uv sync
cd web && npm install && cd ..
uv run python -m quantbench serve
```

Open the printed Web URL. The command binds the API to `127.0.0.1` and creates a local API token for the Web session.
````

- [ ] **Step 6: Verify serve tests**

Run:

```bash
uv run pytest tests/test_serve_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add quantbench/devserver.py quantbench/cli.py web/src/api/client.ts README.md tests/test_serve_cli.py
git commit -m "feat: add one-command local serve"
```

## Task 2: Seed Example Runs For First-Time Users

**Files:**
- Create: `quantbench/examples.py`
- Modify: `quantbench/cli.py`
- Modify: `README.md`
- Test: `tests/test_examples_seed.py`

- [ ] **Step 1: Write example seeding test**

Create `tests/test_examples_seed.py`:

```python
import json


def test_seed_examples_creates_completed_runs(tmp_path):
    from quantbench.examples import seed_examples

    result = seed_examples(tmp_path)

    assert result["created"] == 2
    run_dirs = sorted(tmp_path.glob("run_example_*"))
    assert len(run_dirs) == 2
    for run_dir in run_dirs:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["summary"]
        assert manifest["review"]["verdict"] in {"PROMISING", "STRONG", "WEAK"}
        assert (run_dir / "research_note.md").exists()
        assert (run_dir / "backtest_result.json").exists()
```

Run:

```bash
uv run pytest tests/test_examples_seed.py -q
```

Expected: FAIL because examples module does not exist.

- [ ] **Step 2: Implement deterministic examples**

Create `quantbench/examples.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


EXAMPLES = [
    {
        "run_id": "run_example_crypto_momentum",
        "user_request": "Example: crypto 20 day momentum cross-section",
        "asset_class": "crypto",
        "sharpe": 0.84,
        "verdict": "PROMISING",
        "warning": "Example data is synthetic and for onboarding only.",
    },
    {
        "run_id": "run_example_equity_demo",
        "user_request": "Example: equity demo current S&P 500 momentum",
        "asset_class": "equity",
        "sharpe": 0.42,
        "verdict": "WEAK",
        "warning": "Equity example demonstrates survivorship-bias warnings.",
    },
]


def seed_examples(runs_dir: Path) -> dict[str, int]:
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    for example in EXAMPLES:
        run_dir = runs_dir / example["run_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "run_id": example["run_id"],
            "user_request": example["user_request"],
            "created_at": "2026-07-04T00:00:00+00:00",
            "summary": "Seeded onboarding example. Review the warnings before trusting any result.",
            "metrics": {"sharpe": example["sharpe"], "annual_return": 0.0, "max_drawdown": -0.05},
            "warnings": [example["warning"]],
            "review": {
                "verdict": example["verdict"],
                "verdict_reason": "Seeded example for onboarding.",
                "findings": [
                    {
                        "check": "example_seed",
                        "severity": "info",
                        "message": "This run is a deterministic onboarding example.",
                        "detail": {"asset_class": example["asset_class"]},
                    }
                ],
            },
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "config.yaml").write_text(f"hypothesis: {example['user_request']}\n", encoding="utf-8")
        (run_dir / "backtest_result.json").write_text(
            json.dumps({"metrics": manifest["metrics"], "series": {"timestamp": [], "returns": [], "equity_curve": [], "drawdown": []}}, indent=2),
            encoding="utf-8",
        )
        (run_dir / "review_report.json").write_text(json.dumps(manifest["review"], ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "research_note.md").write_text(
            f"# {example['user_request']}\n\n{example['warning']}\n",
            encoding="utf-8",
        )
        created += 1
    return {"created": created}
```

- [ ] **Step 3: Add CLI command**

In `cli.py`, route:

```python
    if args[0] == "examples":
        _examples(args[1:])
        return
```

Add:

```python
def _examples(args: tuple[str, ...]) -> None:
    if not args or args[0] != "seed":
        raise click.UsageError("examples requires subcommand: seed")
    from quantbench.config import RUNS_DIR
    from quantbench.examples import seed_examples

    result = seed_examples(RUNS_DIR)
    click.echo(f"Seeded {result['created']} example run(s) into {RUNS_DIR}.")
```

- [ ] **Step 4: Update README first-run instructions**

Add:

````markdown
```bash
uv run python -m quantbench examples seed
uv run python -m quantbench serve
```

The example runs let you inspect Reviewer reports, warnings, charts, and artifact structure before spending LLM or market-data API calls.
````

- [ ] **Step 5: Verify examples tests**

Run:

```bash
uv run pytest tests/test_examples_seed.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantbench/examples.py quantbench/cli.py README.md tests/test_examples_seed.py
git commit -m "feat: seed onboarding example runs"
```

## Task 3: Rewrite README As A From-Zero Walkthrough

**Files:**
- Modify: `README.md`
- Test: `tests/test_release_docs.py`

- [ ] **Step 1: Add README coverage test**

Create `tests/test_release_docs.py`:

```python
from pathlib import Path


def test_readme_has_from_zero_walkthrough():
    text = Path("README.md").read_text(encoding="utf-8")

    required = [
        "Prerequisites",
        "DeepSeek",
        "QUANTBENCH_HOME",
        "examples seed",
        "quantbench serve",
        "first 5 minutes",
        "cost",
    ]
    missing = [item for item in required if item not in text]
    assert missing == []
```

Run:

```bash
uv run pytest tests/test_release_docs.py::test_readme_has_from_zero_walkthrough -q
```

Expected: FAIL until README is rewritten.

- [ ] **Step 2: Add prerequisites section**

README content:

```markdown
## Prerequisites

- macOS or Linux
- Python 3.11+
- uv
- Node.js 22+
- A DeepSeek-compatible API key configured for LiteLLM
```

- [ ] **Step 3: Add API key instructions**

Use a local-env example:

````markdown
Create `.env` in the repository or `~/.quantbench/.env`:

```bash
DEEPSEEK_API_KEY=your_key_here
```

Do not commit `.env`.
````

- [ ] **Step 4: Add first 5 minutes path**

```markdown
## First 5 Minutes

1. Seed examples: `uv run python -m quantbench examples seed`.
2. Start the app: `uv run python -m quantbench serve`.
3. Open the printed Web URL.
4. Click the seeded crypto example.
5. Read warnings, Reviewer verdict, `review_report.json`, and `research_note.md` before running a new request.
```

- [ ] **Step 5: Add cost framing**

```markdown
## Cost Expectations

Single runs call the Coordinator and may call the Critic. The manifest records `llm_usage` after completion. Before launch use, treat every new natural-language run as a paid API call and prefer seeded examples for exploration.
```

Task 5 will replace this with a concrete preflight estimate.

- [ ] **Step 6: Verify README test**

Run:

```bash
uv run pytest tests/test_release_docs.py::test_readme_has_from_zero_walkthrough -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add README.md tests/test_release_docs.py
git commit -m "docs: add from-zero launch walkthrough"
```

## Task 4: Move Internal Planning Docs Out Of The Root

**Files:**
- Move: `PHASE10.md` to `docs/dev/PHASE10.md`
- Move: `PHASE10_STATS_FOLLOWUP.md` to `docs/dev/PHASE10_STATS_FOLLOWUP.md`
- Move: `PHASE11.md` to `docs/dev/PHASE11.md`
- Move: `PHASE12.md` to `docs/dev/PHASE12.md`
- Move: `PHASE13.md` to `docs/dev/PHASE13.md`
- Move: `PHASE13B.md` to `docs/dev/PHASE13B.md`
- Move: `PHASE13B_HITL_STAGING.md` to `docs/dev/PHASE13B_HITL_STAGING.md`
- Move: `PHASE13B_MCP_CLIENT.md` to `docs/dev/PHASE13B_MCP_CLIENT.md`
- Move: `GAP_ANALYSIS.md` to `docs/dev/GAP_ANALYSIS.md`
- Move: `MEMORY_BUILD_PLAN.md` to `docs/dev/MEMORY_BUILD_PLAN.md`
- Move: `MEMORY_ARCHITECTURE.md` to `docs/dev/MEMORY_ARCHITECTURE.md`
- Move: `VISION.md` to `docs/dev/VISION.md`
- Modify: `README.md`
- Test: `tests/test_release_docs.py`

- [ ] **Step 1: Add root hygiene test**

Extend `tests/test_release_docs.py`:

```python
from pathlib import Path


def test_root_keeps_user_facing_markdown_only():
    internal = [
        path.name
        for path in Path(".").glob("*.md")
        if path.name.startswith("PHASE") or path.name.startswith("MEMORY") or path.name in {"GAP_ANALYSIS.md", "VISION.md"}
    ]

    assert internal == []
```

Run:

```bash
uv run pytest tests/test_release_docs.py::test_root_keeps_user_facing_markdown_only -q
```

Expected: FAIL because internal planning docs are in the root.

- [ ] **Step 2: Move files with git**

Run:

```bash
mkdir -p docs/dev
git mv PHASE10.md docs/dev/PHASE10.md
git mv PHASE10_STATS_FOLLOWUP.md docs/dev/PHASE10_STATS_FOLLOWUP.md
git mv PHASE11.md docs/dev/PHASE11.md
git mv PHASE12.md docs/dev/PHASE12.md
git mv PHASE13.md docs/dev/PHASE13.md
git mv PHASE13B.md docs/dev/PHASE13B.md
git mv PHASE13B_HITL_STAGING.md docs/dev/PHASE13B_HITL_STAGING.md
git mv PHASE13B_MCP_CLIENT.md docs/dev/PHASE13B_MCP_CLIENT.md
git mv GAP_ANALYSIS.md docs/dev/GAP_ANALYSIS.md
git mv MEMORY_BUILD_PLAN.md docs/dev/MEMORY_BUILD_PLAN.md
git mv MEMORY_ARCHITECTURE.md docs/dev/MEMORY_ARCHITECTURE.md
git mv VISION.md docs/dev/VISION.md
```

- [ ] **Step 3: Update README links**

Add:

```markdown
Internal implementation notes live under `docs/dev/`. They are useful for contributors but are not required for first-time use.
```

Update any root-relative links to `docs/dev/...`.

- [ ] **Step 4: Verify docs test and link search**

Run:

```bash
uv run pytest tests/test_release_docs.py -q
rg -n "PHASE|GAP_ANALYSIS|MEMORY_|VISION" README.md LAUNCH_READINESS.md docs/dev
```

Expected: root hygiene test PASS; remaining references point to `docs/dev/` when they are user-facing links.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_release_docs.py docs/dev
git commit -m "docs: move internal planning notes under docs dev"
```

## Task 5: Add Preflight Cost Estimate For Main Run Submission

**Files:**
- Create: `quantbench/agent/cost_estimate.py`
- Modify: `quantbench/api/schemas.py`
- Modify: `quantbench/api/server.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/components/ChatInput.tsx`
- Modify: `web/src/components/ChatPane.tsx`
- Test: `tests/test_cost_estimate.py`
- Test: `web/src/components/ChatInput.test.tsx`

- [ ] **Step 1: Write backend cost estimate test**

Create `tests/test_cost_estimate.py`:

```python
def test_estimate_run_cost_returns_llm_call_range():
    from quantbench.agent.cost_estimate import estimate_run_cost

    estimate = estimate_run_cost("test 20 day momentum on top crypto perpetuals")

    assert estimate["currency"] == "USD"
    assert estimate["estimated_llm_calls_min"] >= 1
    assert estimate["estimated_llm_calls_max"] >= estimate["estimated_llm_calls_min"]
    assert "Coordinator" in estimate["notes"][0]
```

Run:

```bash
uv run pytest tests/test_cost_estimate.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 2: Implement deterministic estimate**

Create `quantbench/agent/cost_estimate.py`:

```python
from __future__ import annotations


def estimate_run_cost(user_request: str) -> dict:
    words = len(user_request.split())
    likely_cross_sectional = any(token in user_request.lower() for token in ["sp500", "s&p", "cross", "section", "截面", "universe", "crypto"])
    min_calls = 2 if likely_cross_sectional else 1
    max_calls = 6 if likely_cross_sectional else 4
    return {
        "currency": "USD",
        "estimated_llm_calls_min": min_calls,
        "estimated_llm_calls_max": max_calls,
        "request_words": words,
        "estimated_cost_usd_min": None,
        "estimated_cost_usd_max": None,
        "notes": [
            "Coordinator call is required for each natural-language run.",
            "Critic and sub-agent calls may run after the deterministic backtest.",
            "Exact cost is recorded after completion in manifest.llm_usage.",
        ],
    }
```

- [ ] **Step 3: Add API schema and endpoint**

In `schemas.py`:

```python
class EstimateRunRequest(BaseModel):
    request: str


class EstimateRunResponse(BaseModel):
    currency: str
    estimated_llm_calls_min: int
    estimated_llm_calls_max: int
    request_words: int
    estimated_cost_usd_min: float | None = None
    estimated_cost_usd_max: float | None = None
    notes: list[str]
```

In `server.py`:

```python
@app.post("/api/runs/estimate", response_model=EstimateRunResponse)
def estimate_run(payload: EstimateRunRequest) -> EstimateRunResponse:
    if not payload.request.strip():
        raise HTTPException(status_code=400, detail="request must not be empty")
    from quantbench.agent.cost_estimate import estimate_run_cost

    return EstimateRunResponse(**estimate_run_cost(payload.request))
```

- [ ] **Step 4: Add API client function**

In `web/src/api/client.ts`:

```ts
export interface RunCostEstimate {
  currency: string;
  estimated_llm_calls_min: number;
  estimated_llm_calls_max: number;
  request_words: number;
  estimated_cost_usd_min: number | null;
  estimated_cost_usd_max: number | null;
  notes: string[];
}

export function estimateRun(userRequest: string): Promise<RunCostEstimate> {
  return request<RunCostEstimate>("/runs/estimate", {
    method: "POST",
    body: JSON.stringify({ request: userRequest }),
  });
}
```

- [ ] **Step 5: Show preflight in ChatInput**

Add a compact estimate row after the user types and before submit. If the codebase already has `ChatPane` submit ownership, keep the API call in `ChatPane` and pass the estimate into `ChatInput`.

Visible text should be factual:

```tsx
{estimate && (
  <div className="text-xs text-warm-500">
    Estimated LLM calls: {estimate.estimated_llm_calls_min}-{estimate.estimated_llm_calls_max}. Exact usage is recorded after completion.
  </div>
)}
```

- [ ] **Step 6: Add frontend test**

In `web/src/components/ChatInput.test.tsx`:

```tsx
it("shows preflight LLM call estimate", () => {
  render(
    <ChatInput
      disabled={false}
      isRunning={false}
      onSubmit={vi.fn()}
      onStop={vi.fn()}
      costEstimate={{
        currency: "USD",
        estimated_llm_calls_min: 2,
        estimated_llm_calls_max: 6,
        request_words: 8,
        estimated_cost_usd_min: null,
        estimated_cost_usd_max: null,
        notes: [],
      }}
    />,
  );

  expect(screen.getByText(/Estimated LLM calls: 2-6/i)).toBeInTheDocument();
});
```

- [ ] **Step 7: Verify tests**

Run:

```bash
uv run pytest tests/test_cost_estimate.py tests/test_api.py -q
cd web && npm test -- ChatInput.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add quantbench/agent/cost_estimate.py quantbench/api/schemas.py quantbench/api/server.py web/src/api/client.ts web/src/components/ChatInput.tsx web/src/components/ChatPane.tsx web/src/components/ChatInput.test.tsx tests/test_cost_estimate.py
git commit -m "feat: show preflight run cost estimate"
```

## Task 6: Put Risk Disclaimers On Handoff Surfaces

**Files:**
- Modify: `quantbench/factors/signal_export.py`
- Modify: `web/src/components/ArtifactInspector.tsx`
- Modify: `web/src/components/WarningBanner.tsx`
- Test: `tests/test_signal_export.py`
- Test: `web/src/components/WarningBanner.test.tsx`

- [ ] **Step 1: Add signal export disclaimer test**

Add to `tests/test_signal_export.py`:

```python
def test_supported_signal_export_includes_research_disclaimer(monkeypatch):
    import pandas as pd
    from quantbench.factors.entry import FactorEntry
    from quantbench.factors.signal_export import build_signal_export

    monkeypatch.setattr(
        "quantbench.factors.signal_export.refresh_and_recompute_weights",
        lambda run_id, conn=None: pd.Series({"AAA": 0.5, "BBB": -0.5}, name=pd.Timestamp("2026-07-04", tz="UTC")),
    )
    entry = FactorEntry(
        name="cross_momentum",
        family="momentum",
        asset_class="equity",
        code="def compute(df):\n    return df.close.pct_change()",
        parameters=[],
        source_run_id="run_cross",
        source_verdict="PROMISING",
        source_metrics={"sharpe": 1.0},
        source_findings=[],
        lifecycle_state="research",
        saved_at="2026-07-04T00:00:00+00:00",
        notes="",
        saved_from_rejected=False,
    )

    payload = build_signal_export(entry)

    assert "not an order" in payload["risk_disclaimer"].lower()
```

Run:

```bash
uv run pytest tests/test_signal_export.py::test_supported_signal_export_includes_research_disclaimer -q
```

Expected: FAIL until disclaimer is added.

- [ ] **Step 2: Update `signal_export.py`**

Add to supported payload:

```python
"risk_disclaimer": (
    "Research signal export is not an order, investment recommendation, or permission to trade. "
    "Review source verdict, limitations, lifecycle state, and current data freshness before use."
),
```

- [ ] **Step 3: Add Web disclaimer near artifacts**

In `ArtifactInspector.tsx`, when opening `signal_export` JSON or `factor` export artifacts, display:

```tsx
<div className="border border-warn-200 bg-warn-50 text-warn-900 text-xs rounded-md p-2">
  Research artifacts are not trading instructions. Review warnings and limitations before use.
</div>
```

Use an existing warning tone class if available.

- [ ] **Step 4: Add frontend warning test**

In `WarningBanner.test.tsx`:

```tsx
it("renders research risk warnings", () => {
  render(<WarningBanner warnings={["Research artifacts are not trading instructions."]} />);

  expect(screen.getByText(/not trading instructions/i)).toBeInTheDocument();
});
```

- [ ] **Step 5: Verify tests**

Run:

```bash
uv run pytest tests/test_signal_export.py -q
cd web && npm test -- WarningBanner.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantbench/factors/signal_export.py web/src/components/ArtifactInspector.tsx web/src/components/WarningBanner.tsx web/src/components/WarningBanner.test.tsx tests/test_signal_export.py
git commit -m "fix: add research risk disclaimers to handoff surfaces"
```

## Task 7: Add Release Discipline

**Files:**
- Create: `CHANGELOG.md`
- Create: `docs/RELEASE.md`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Test: `tests/test_release_docs.py`

- [ ] **Step 1: Add release docs tests**

Extend `tests/test_release_docs.py`:

```python
def test_release_docs_exist_and_cover_required_checks():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    release = Path("docs/RELEASE.md").read_text(encoding="utf-8")

    assert "0.1.0" in changelog
    for item in ["pytest", "frontend", "Playwright", "manual LLM eval", "tag"]:
        assert item in release
```

Run:

```bash
uv run pytest tests/test_release_docs.py::test_release_docs_exist_and_cover_required_checks -q
```

Expected: FAIL because release docs are missing.

- [ ] **Step 2: Create `CHANGELOG.md`**

```markdown
# Changelog

## 0.1.0-alpha - 2026-07-04

- Local AI workbench for reproducible quant research runs.
- Deterministic Reviewer with statistical, execution, data-quality, and cost findings.
- FastAPI + React local workspace for run browsing, artifacts, library, comparison, and paper workflows.
- Launch limitations: macOS/Linux only; research artifacts are not investment advice; some data providers retain documented survivorship and coverage limits.
```

- [ ] **Step 3: Create `docs/RELEASE.md`**

```markdown
# Release Checklist

1. Run backend tests: `uv run pytest -q`.
2. Run frontend lint/unit/build: `cd web && npm run lint && npm test && npm run build`.
3. Run Playwright: `cd web && npm run test:e2e`.
4. Run wheel smoke: `uv run python -m build` and install the wheel in a clean venv.
5. Run manual LLM eval when an API key is available: `uv run python -m quantbench eval llm --cases quantbench/evals/llm_cases.yaml`.
6. Seed examples in a clean `QUANTBENCH_HOME` and start `quantbench serve`.
7. Review `LAUNCH_READINESS.md` and update resolved launch gaps.
8. Bump `pyproject.toml` version and `CHANGELOG.md`.
9. Create a signed git tag: `git tag -s v0.1.0-alpha -m "QuantBench v0.1.0-alpha"`.
10. Publish release notes with platform, API safety, data limitations, and risk disclaimer.
```

- [ ] **Step 4: Align version text**

If this is pre-release, set:

```toml
version = "0.1.0a0"
```

If Python packaging version policy should stay stable, keep `0.1.0` and use `CHANGELOG.md` to mark alpha. Do not use a non-PEP 440 version string in `pyproject.toml`.

- [ ] **Step 5: Link release docs from README**

Add:

```markdown
Release discipline and preflight checks live in `docs/RELEASE.md`; user-facing changes are tracked in `CHANGELOG.md`.
```

- [ ] **Step 6: Verify release docs**

Run:

```bash
uv run pytest tests/test_release_docs.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add CHANGELOG.md docs/RELEASE.md pyproject.toml README.md tests/test_release_docs.py
git commit -m "docs: add changelog and release checklist"
```

## Task 8: Full Product-Layer Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run product-focused backend tests**

```bash
uv run pytest tests/test_serve_cli.py tests/test_examples_seed.py tests/test_cost_estimate.py tests/test_release_docs.py tests/test_signal_export.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests touched by product work**

```bash
cd web && npm test -- ChatInput.test.tsx WarningBanner.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run full backend and frontend suites**

```bash
uv run pytest -q
cd web && npm run lint && npm test && npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual first-run rehearsal**

Use a clean home:

```bash
QUANTBENCH_HOME=/tmp/qb-first-run uv run python -m quantbench examples seed
QUANTBENCH_HOME=/tmp/qb-first-run uv run python -m quantbench serve --dry-run
```

Expected: examples are created under `/tmp/qb-first-run/runs`, and serve prints local API/Web URLs plus a token.

- [ ] **Step 5: Update launch readiness**

In `LAUNCH_READINESS.md` section 三:

- Mark one-command startup done.
- Mark example run seed done.
- Mark from-zero walkthrough done.
- Mark internal docs moved.
- Mark cost preflight done.
- Mark handoff-surface disclaimers done.
- Mark changelog/release checklist done.

- [ ] **Step 6: Commit docs update**

```bash
git add LAUNCH_READINESS.md
git commit -m "docs: mark product launch readiness gaps resolved"
```

## Acceptance Criteria

- A new user can run `examples seed` and `serve` without knowing the backend/frontend command split.
- Seeded examples show completed runs, warnings, Reviewer output, and research notes without LLM/API spend.
- README starts with prerequisites, API key setup, first 5 minutes, cost expectations, and risk posture.
- Internal planning docs are no longer mixed into the root user-facing file list.
- Main run submission has a preflight LLM call estimate.
- Factor export and Web artifact handoff surfaces display research-risk disclaimers.
- `CHANGELOG.md` and `docs/RELEASE.md` exist and are covered by tests.
