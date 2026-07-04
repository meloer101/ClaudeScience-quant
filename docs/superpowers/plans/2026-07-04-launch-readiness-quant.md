# Launch Readiness Quant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决 `LAUNCH_READINESS.md`「二、量化角度」列出的可信度缺口：美股截面幸存者偏差叙事不对称、crypto PIT 对新用户为空、LLM 判断无回归评测、数据复现/永续数据 schema/单资产导出债务缺少首发声明。

**Architecture:** 不把首发伪装成“所有资产同等可靠”。新增一个轻量 `trust_policy` 层，把资产类别、provider 覆盖能力和 universe 限制转成文档、manifest 与 Reviewer 可见标签。Crypto PIT 通过 packaged seed 注入 DuckDB，LLM eval 作为手动、有成本、有 fixture 的命令加入，而不是塞进普通 CI。剩余研究债以显式 limitation 进入 README、factor export 和 release checklist，避免静默承诺。

**Tech Stack:** Python 3.11+, pandas, DuckDB, pytest, click, YAML/JSON fixtures, LiteLLM-compatible LLM client, existing Reviewer/ArtifactStore.

---

## Scope Map

| LAUNCH_READINESS quant item | Plan tasks |
|---|---|
| Equity 截面方向性风险仍未解除 | Task 1, Task 2 |
| README 把 equity 与 crypto 并列宣传 | Task 1 |
| Crypto PIT 对新用户为空 | Task 3 |
| LLM 侧无评测 | Task 4 |
| 数据分片保留策略缺失 | Task 5 |
| `open_interest` / `PerpetualData` schema 未落地 | Task 6 |
| 单资产因子无信号导出 | Task 7 |

本计划默认 B1 funding 修复已先执行。若 B1 未执行，Task 1 的 README/产品叙事必须继续把 crypto 标为“本地 alpha，不作主打”。

## File Structure

- Create: `quantbench/review/trust_policy.py`
  - Map universe/provider facts into launch-facing trust tiers and limitations.
- Modify: `quantbench/review/report.py`
  - Add optional trust-policy finding.
- Modify: `quantbench/agent/coordinator.py`, `quantbench/agent/tools/screening.py`
  - Include trust policy in config, manifest context, and Reviewer.
- Modify: `README.md`
  - Reposition equity current-snapshot runs as demo/teaching; crypto as launch-primary only after funding fix.
- Create: `quantbench/data/seeds/crypto_universe_snapshot_seed.json`
  - Seed daily crypto universe snapshots for a bounded date window.
- Create: `quantbench/data/seed_crypto.py`
  - Load seed snapshots into DuckDB idempotently.
- Modify: `quantbench/cli.py`
  - Add `universe seed-crypto`.
- Create: `quantbench/evals/llm_cases.yaml`
  - Small launch eval set for natural-language requests.
- Create: `quantbench/evals/llm_runner.py`
  - Run eval cases against a real or fake LLM client.
- Modify: `quantbench/cli.py`
  - Add `eval llm`.
- Create: `quantbench/data/retention.py`
  - Data-slice pinning and retention audit helpers.
- Modify: `quantbench/cli.py`
  - Add `cache audit` or extend `rerun` diagnostics.
- Create: `quantbench/data/perpetual.py`
  - Typed perpetual market schema with optional `open_interest`.
- Modify: `quantbench/factors/signal_export.py`
  - Add explicit single-asset unsupported limitation payload.
- Modify tests:
  - `tests/test_launch_trust_policy.py`
  - `tests/test_crypto_universe_snapshot.py`
  - `tests/test_llm_eval.py`
  - `tests/test_data_retention.py`
  - `tests/test_phase5_crypto_universe.py`
  - `tests/test_signal_export.py`

## Task 1: Add Launch Trust Policy For Asset Claims

**Files:**
- Create: `quantbench/review/trust_policy.py`
- Modify: `quantbench/review/report.py`
- Modify: `quantbench/agent/coordinator.py`
- Modify: `quantbench/agent/tools/screening.py`
- Test: `tests/test_launch_trust_policy.py`

- [ ] **Step 1: Write trust-policy tests**

Create `tests/test_launch_trust_policy.py`:

```python
from quantbench.data.universe import UniverseDefinition


def test_current_sp500_is_launch_demo_tier_until_delisted_data_source_exists():
    from quantbench.review.trust_policy import launch_trust_policy

    universe = UniverseDefinition(
        name="sp500",
        as_of_date="2026-07-04",
        symbols=["AAPL", "MSFT"],
        point_in_time=False,
        survivorship_bias_note="current constituents",
        source="wikipedia",
        asset_class="equity",
        covers_delisted=False,
    )

    policy = launch_trust_policy(universe, data_meta={"covers_delisted": False})

    assert policy["tier"] == "demo"
    assert policy["asset_class"] == "equity"
    assert any("survivorship" in item.lower() for item in policy["limitations"])


def test_crypto_current_universe_is_launch_primary_only_when_funding_complete():
    from quantbench.review.trust_policy import launch_trust_policy

    universe = UniverseDefinition(
        name="top_usdt_perpetual",
        as_of_date="2026-07-04",
        symbols=["BTC/USDT", "ETH/USDT"],
        point_in_time=False,
        survivorship_bias_note="current ranking",
        source="ccxt_okx_tickers",
        asset_class="crypto",
    )

    complete = launch_trust_policy(
        universe,
        funding_meta={"alignment": {"coverage_ratio": 1.0, "missing_period_symbol_pairs": 0}, "failed": {}},
    )
    incomplete = launch_trust_policy(
        universe,
        funding_meta={"alignment": {"coverage_ratio": 0.5, "missing_period_symbol_pairs": 10}, "failed": {}},
    )

    assert complete["tier"] == "launch_primary"
    assert incomplete["tier"] == "alpha_only"
```

Run:

```bash
uv run pytest tests/test_launch_trust_policy.py -q
```

Expected: FAIL because `quantbench.review.trust_policy` does not exist.

- [ ] **Step 2: Implement `trust_policy.py`**

```python
from __future__ import annotations

from typing import Any

from quantbench.data.universe import UniverseDefinition


def launch_trust_policy(
    universe: UniverseDefinition | None,
    *,
    data_meta: dict[str, Any] | None = None,
    funding_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if universe is None:
        return {"tier": "unknown", "asset_class": "unknown", "limitations": ["No universe metadata was recorded."]}

    limitations: list[str] = []
    tier = "research"

    if universe.asset_class == "equity":
        if not universe.point_in_time:
            limitations.append(
                "Equity current-constituent runs are demonstration/teaching runs; survivorship bias can change factor direction."
            )
            tier = "demo"
        elif not bool((data_meta or {}).get("covers_delisted")):
            limitations.append(
                "Equity PIT universe definition is available, but delisted-member price coverage is incomplete."
            )
            tier = "research"
        else:
            tier = "research_ready"

    elif universe.asset_class == "crypto":
        alignment = (funding_meta or {}).get("alignment") or {}
        coverage = float(alignment.get("coverage_ratio", 0.0) or 0.0)
        missing_pairs = int(alignment.get("missing_period_symbol_pairs", 0) or 0)
        failed = funding_meta.get("failed") if isinstance(funding_meta, dict) else {}
        if coverage >= 0.98 and missing_pairs == 0 and not failed:
            tier = "launch_primary"
        else:
            tier = "alpha_only"
            limitations.append("Crypto funding coverage is incomplete; funding-adjusted Sharpe may still be biased.")
        if not universe.point_in_time:
            limitations.append("Crypto current top-N universe is not point-in-time; historical ranking bias remains.")

    else:
        tier = "research"
        limitations.append(f"Asset class {universe.asset_class!r} has no launch trust policy.")

    return {
        "tier": tier,
        "asset_class": universe.asset_class,
        "universe": universe.name,
        "point_in_time": universe.point_in_time,
        "covers_delisted": bool((data_meta or {}).get("covers_delisted") or universe.covers_delisted),
        "limitations": limitations,
    }
```

- [ ] **Step 3: Add Reviewer finding**

In `review/report.py`, add optional parameter:

```python
launch_trust: dict[str, Any] | None = None,
```

Append:

```python
if launch_trust is not None:
    findings.append(_launch_trust_finding(launch_trust))
```

Implement:

```python
def _launch_trust_finding(detail: dict[str, Any]) -> ReviewFinding:
    tier = str(detail.get("tier") or "unknown")
    limitations = list(detail.get("limitations") or [])
    if tier == "demo":
        return ReviewFinding("launch_trust_policy", "warning", "Launch policy marks this universe as demo/teaching only.", detail)
    if tier == "alpha_only":
        return ReviewFinding("launch_trust_policy", "warning", "Launch policy marks this run as local alpha only.", detail)
    if limitations:
        return ReviewFinding("launch_trust_policy", "info", "Launch policy recorded limitations for this run.", detail)
    return ReviewFinding("launch_trust_policy", "pass", f"Launch policy tier is {tier}.", detail)
```

- [ ] **Step 4: Wire Coordinator and screening**

After data/funding meta is known:

```python
from quantbench.review.trust_policy import launch_trust_policy

ctx.launch_trust = launch_trust_policy(ctx.universe, data_meta=cache_meta, funding_meta=funding_meta)
```

Pass `launch_trust=ctx.launch_trust` to `run_review`, save it in config:

```python
"launch_trust": ctx.launch_trust,
```

In screening, compute policy once and pass into child config/review.

- [ ] **Step 5: Verify trust-policy tests**

Run:

```bash
uv run pytest tests/test_launch_trust_policy.py tests/test_phase5_crypto_universe.py tests/test_phase8_factor_screening.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantbench/review/trust_policy.py quantbench/review/report.py quantbench/agent/coordinator.py quantbench/agent/tools/screening.py tests/test_launch_trust_policy.py
git commit -m "feat: add launch trust policy for asset claims"
```

## Task 2: Calibrate README And UI Copy To Trust Tiers

**Files:**
- Modify: `README.md`
- Modify: `web/src/components/WarningBanner.tsx`
- Modify: `web/src/components/ArtifactInspector.tsx`
- Test: `tests/test_launch_trust_policy.py`
- Test: `web/src/components/WarningBanner.test.tsx`

- [ ] **Step 1: Add docs assertion for asset positioning**

Extend `tests/test_launch_trust_policy.py`:

```python
from pathlib import Path


def test_readme_does_not_present_equity_and_crypto_as_equally_launch_ready():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "美股截面" in text
    assert "survivorship" in text.lower()
    assert "demo" in text.lower() or "演示" in text
    assert "crypto" in text.lower()
    assert "funding" in text.lower()
```

Run:

```bash
uv run pytest tests/test_launch_trust_policy.py::test_readme_does_not_present_equity_and_crypto_as_equally_launch_ready -q
```

Expected: FAIL until README is updated.

- [ ] **Step 2: Update README project positioning**

Replace the asset support bullet with:

```markdown
- Crypto perpetual 截面是首发主研究路径，但必须使用 funding 修复后的版本，且每个 run 会记录 funding 覆盖率。
- 美股截面当前适合教学/演示和研究框架验证；若未接入覆盖退市成员的付费数据源，current S&P 500 结果可能存在方向性幸存者偏差。
```

Add a “Launch Trust Tiers” section:

```markdown
## Launch Trust Tiers

- `launch_primary`: 首发主路径；数据链路和成本模型达到当前项目承诺。
- `research_ready`: 可认真研究，但仍需阅读 Reviewer 限制。
- `demo`: 教学/演示用途，不能按完整历史投资结论解读。
- `alpha_only`: 仅适合受信任用户本地 alpha，公开叙事不得作为主打。
```

- [ ] **Step 3: Surface trust tier in Web warning banner**

If `RunDetail` warnings already include Reviewer warnings, add formatting for `launch_trust_policy` warnings in `WarningBanner.tsx`:

```tsx
function warningTone(message: string) {
  if (message.includes("launch_trust_policy")) return "trust";
  if (message.includes("CRITICAL")) return "danger";
  return "warning";
}
```

Keep text minimal and do not add a marketing explanation in the UI.

- [ ] **Step 4: Add frontend test**

In `web/src/components/WarningBanner.test.tsx`:

```tsx
it("renders launch trust policy warnings", () => {
  render(<WarningBanner warnings={["Reviewer WARNING [launch_trust_policy]: Launch policy marks this universe as demo/teaching only."]} />);

  expect(screen.getByText(/launch policy marks this universe/i)).toBeInTheDocument();
});
```

- [ ] **Step 5: Verify docs and UI tests**

Run:

```bash
uv run pytest tests/test_launch_trust_policy.py -q
cd web && npm test -- WarningBanner.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md web/src/components/WarningBanner.tsx web/src/components/WarningBanner.test.tsx tests/test_launch_trust_policy.py
git commit -m "docs: calibrate launch asset trust positioning"
```

## Task 3: Ship A Crypto PIT Snapshot Seed

**Files:**
- Create: `quantbench/data/seeds/crypto_universe_snapshot_seed.json`
- Create: `quantbench/data/seed_crypto.py`
- Modify: `quantbench/data/warehouse.py`
- Modify: `quantbench/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_crypto_universe_snapshot.py`

- [ ] **Step 1: Add failing seed-load test**

Add to `tests/test_crypto_universe_snapshot.py`:

```python
def test_seed_crypto_universe_snapshots_is_idempotent(tmp_path):
    from quantbench.data.seed_crypto import seed_crypto_universe_snapshots
    from quantbench.data.warehouse import get_connection, query_crypto_universe_snapshot

    conn = get_connection(tmp_path / "seed.duckdb")

    first = seed_crypto_universe_snapshots(conn)
    second = seed_crypto_universe_snapshots(conn)

    assert first["rows_written"] > 0
    assert second["rows_written"] == first["rows_written"]
    symbols = query_crypto_universe_snapshot(conn, first["start_date"])
    assert symbols is not None
    assert "BTC/USDT" in symbols or "BTC/USDT:USDT" in symbols
```

Run:

```bash
uv run pytest tests/test_crypto_universe_snapshot.py::test_seed_crypto_universe_snapshots_is_idempotent -q
```

Expected: FAIL because seed loader does not exist.

- [ ] **Step 2: Add seed JSON**

Create `quantbench/data/seeds/crypto_universe_snapshot_seed.json` with a compact bounded seed:

```json
{
  "source": "QuantBench launch seed, manually curated from active USDT perpetuals for onboarding",
  "quote": "USDT",
  "snapshots": [
    {
      "as_of_date": "2026-07-01",
      "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    },
    {
      "as_of_date": "2026-07-02",
      "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    },
    {
      "as_of_date": "2026-07-03",
      "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    }
  ]
}
```

This seed is only for first-run PIT mechanics, not a historical backfill.

- [ ] **Step 3: Implement seed loader**

Create `quantbench/data/seed_crypto.py`:

```python
from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import pandas as pd

from quantbench.data.warehouse import CRYPTO_UNIVERSE_SNAPSHOT_TABLE, ensure_schema


def load_crypto_universe_seed() -> dict[str, Any]:
    path = files("quantbench.data.seeds").joinpath("crypto_universe_snapshot_seed.json")
    return json.loads(path.read_text(encoding="utf-8"))


def seed_crypto_universe_snapshots(conn) -> dict[str, Any]:
    ensure_schema(conn)
    payload = load_crypto_universe_seed()
    rows = []
    for snapshot in payload["snapshots"]:
        as_of_date = pd.Timestamp(snapshot["as_of_date"]).date()
        for rank, symbol in enumerate(snapshot["symbols"], start=1):
            rows.append({"as_of_date": as_of_date, "symbol": symbol, "quote_volume_24h": None, "rank": rank})
    frame = pd.DataFrame(rows)
    conn.register("_seed_crypto_universe", frame)
    try:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {CRYPTO_UNIVERSE_SNAPSHOT_TABLE}
            SELECT as_of_date, symbol, quote_volume_24h, rank
            FROM _seed_crypto_universe
            """
        )
    finally:
        conn.unregister("_seed_crypto_universe")
    return {
        "rows_written": len(rows),
        "snapshots": len(payload["snapshots"]),
        "start_date": payload["snapshots"][0]["as_of_date"],
        "end_date": payload["snapshots"][-1]["as_of_date"],
        "source": payload["source"],
    }
```

Add `quantbench/data/seeds/__init__.py`.

- [ ] **Step 4: Include seed package data**

In `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"quantbench/data/seeds/crypto_universe_snapshot_seed.json" = "quantbench/data/seeds/crypto_universe_snapshot_seed.json"
```

- [ ] **Step 5: Add CLI command**

In `cli.py`, inside `_universe`:

```python
    if args[0] == "seed-crypto":
        from quantbench.data.seed_crypto import seed_crypto_universe_snapshots
        from quantbench.data.warehouse import get_connection

        result = seed_crypto_universe_snapshots(get_connection())
        click.echo(
            f"Seeded {result['rows_written']} crypto universe snapshot row(s) "
            f"from {result['start_date']} to {result['end_date']}."
        )
        return
```

Update usage error:

```python
"universe requires a subcommand: snapshot-crypto/seed-crypto"
```

- [ ] **Step 6: Verify seed tests**

Run:

```bash
uv run pytest tests/test_crypto_universe_snapshot.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add quantbench/data/seeds/__init__.py quantbench/data/seeds/crypto_universe_snapshot_seed.json quantbench/data/seed_crypto.py quantbench/cli.py pyproject.toml tests/test_crypto_universe_snapshot.py
git commit -m "feat: add crypto universe PIT seed snapshots"
```

## Task 4: Add Manual LLM Regression Eval

**Files:**
- Create: `quantbench/evals/__init__.py`
- Create: `quantbench/evals/llm_cases.yaml`
- Create: `quantbench/evals/llm_runner.py`
- Modify: `quantbench/cli.py`
- Test: `tests/test_llm_eval.py`

- [ ] **Step 1: Write fake-client eval test**

Create `tests/test_llm_eval.py`:

```python
from types import SimpleNamespace


class FakeEvalLLM:
    model = "fake-eval"

    def chat(self, messages, tools=None):
        tool_call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(
                name="build_universe",
                arguments='{"universe_name":"top_30_usdt_perpetual","as_of_date":"2026-07-04","limit":30}',
            ),
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))])


def test_llm_eval_case_checks_expected_tool_name():
    from quantbench.evals.llm_runner import LlmEvalCase, run_case

    case = LlmEvalCase(
        name="crypto_universe",
        request="Build top 30 crypto perpetual universe.",
        expected_first_tool="build_universe",
        expected_arguments={"universe_name": "top_30_usdt_perpetual"},
    )

    result = run_case(FakeEvalLLM(), case)

    assert result.passed is True
    assert result.actual_first_tool == "build_universe"
```

Run:

```bash
uv run pytest tests/test_llm_eval.py -q
```

Expected: FAIL because eval runner does not exist.

- [ ] **Step 2: Add eval case schema and runner**

Create `quantbench/evals/llm_runner.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from quantbench.agent.prompts import SYSTEM_PROMPT


@dataclass(frozen=True)
class LlmEvalCase:
    name: str
    request: str
    expected_first_tool: str
    expected_arguments: dict[str, Any]


@dataclass(frozen=True)
class LlmEvalResult:
    name: str
    passed: bool
    actual_first_tool: str | None
    mismatches: list[str]


def load_cases(path: Path) -> list[LlmEvalCase]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [LlmEvalCase(**item) for item in payload["cases"]]


def run_case(llm, case: LlmEvalCase) -> LlmEvalResult:
    response = llm.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case.request},
        ],
        tools=[],
    )
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    actual_first_tool = None
    actual_args: dict[str, Any] = {}
    if tool_calls:
        actual_first_tool = tool_calls[0].function.name
        actual_args = json.loads(tool_calls[0].function.arguments or "{}")

    mismatches = []
    if actual_first_tool != case.expected_first_tool:
        mismatches.append(f"expected first tool {case.expected_first_tool}, got {actual_first_tool}")
    for key, expected_value in case.expected_arguments.items():
        if actual_args.get(key) != expected_value:
            mismatches.append(f"expected argument {key}={expected_value!r}, got {actual_args.get(key)!r}")
    return LlmEvalResult(case.name, not mismatches, actual_first_tool, mismatches)


def run_cases(llm, cases: list[LlmEvalCase]) -> list[LlmEvalResult]:
    return [run_case(llm, case) for case in cases]
```

- [ ] **Step 3: Add eval fixtures**

Create `quantbench/evals/llm_cases.yaml`:

```yaml
cases:
  - name: crypto_cross_sectional_momentum
    request: "Build a top 30 USDT perpetual universe and test 20 day momentum from 2023-01-01 to 2024-12-31."
    expected_first_tool: build_universe
    expected_arguments:
      universe_name: top_30_usdt_perpetual
  - name: equity_demo_momentum
    request: "Run a quick S&P 500 demo for 20 day momentum on 50 symbols."
    expected_first_tool: build_universe
    expected_arguments:
      universe_name: sp500
  - name: library_question
    request: "Across my past experiments, which promising crypto factors have the highest Sharpe?"
    expected_first_tool: none
    expected_arguments: {}
```

For a no-tool case, runner should treat assistant text as `actual_first_tool = "none"`.

- [ ] **Step 4: Add CLI command**

In `cli.py`, route:

```python
    if args[0] == "eval":
        _eval(args[1:])
        return
```

Add:

```python
def _eval(args: tuple[str, ...]) -> None:
    if not args or args[0] != "llm":
        raise click.UsageError("eval requires subcommand: llm")
    from pathlib import Path
    from quantbench.agent.llm import LLMClient
    from quantbench.config import DEFAULT_MODEL
    from quantbench.evals.llm_runner import load_cases, run_cases

    path = Path(_option_value(args[1:], "--cases") or "quantbench/evals/llm_cases.yaml")
    results = run_cases(LLMClient(DEFAULT_MODEL), load_cases(path))
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        click.echo(f"{status} {result.name}: {', '.join(result.mismatches) if result.mismatches else result.actual_first_tool}")
    if any(not result.passed for result in results):
        raise click.ClickException("LLM eval failed")
```

- [ ] **Step 5: Verify fake eval tests**

Run:

```bash
uv run pytest tests/test_llm_eval.py -q
```

Expected: PASS.

- [ ] **Step 6: Document manual eval**

README:

````markdown
Manual LLM regression eval:

```bash
uv run python -m quantbench eval llm --cases quantbench/evals/llm_cases.yaml
```

This command uses the configured LLM and may incur API cost. It is intentionally not part of regular CI.
````

- [ ] **Step 7: Commit**

```bash
git add quantbench/evals/__init__.py quantbench/evals/llm_cases.yaml quantbench/evals/llm_runner.py quantbench/cli.py README.md tests/test_llm_eval.py
git commit -m "feat: add manual llm regression eval"
```

## Task 5: Add Data Retention Audit For Reproducible Reruns

**Files:**
- Create: `quantbench/data/retention.py`
- Modify: `quantbench/cli.py`
- Modify: `quantbench/artifact/store.py`
- Test: `tests/test_data_retention.py`

- [ ] **Step 1: Write retention audit tests**

Create `tests/test_data_retention.py`:

```python
import json


def test_retention_audit_flags_missing_manifest_slices(tmp_path):
    from quantbench.data.retention import audit_run_data_slices

    run_dir = tmp_path / "run_1"
    run_dir.mkdir()
    missing_path = tmp_path / "missing.parquet"
    (run_dir / "manifest.json").write_text(
        json.dumps({"data_slices": [{"path": str(missing_path), "content_hash": "abc", "symbol": "AAA"}]}),
        encoding="utf-8",
    )

    report = audit_run_data_slices(run_dir)

    assert report["status"] == "missing"
    assert report["missing"][0]["symbol"] == "AAA"
```

Run:

```bash
uv run pytest tests/test_data_retention.py -q
```

Expected: FAIL because retention module does not exist.

- [ ] **Step 2: Implement retention audit helper**

Create `quantbench/data/retention.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantbench.data.cache import file_sha256


def audit_run_data_slices(run_dir: Path) -> dict[str, Any]:
    manifest_path = Path(run_dir) / "manifest.json"
    if not manifest_path.exists():
        return {"status": "no_manifest", "missing": [], "drifted": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = []
    drifted = []
    for item in manifest.get("data_slices") or []:
        path = item.get("path")
        expected = item.get("content_hash")
        if not path:
            missing.append(item)
            continue
        file_path = Path(path)
        if not file_path.exists():
            missing.append(item)
            continue
        if expected and file_sha256(file_path) != expected:
            drifted.append(item)
    if missing:
        status = "missing"
    elif drifted:
        status = "drifted"
    else:
        status = "ok"
    return {"status": status, "missing": missing, "drifted": drifted}
```

- [ ] **Step 3: Extend CLI diagnostics**

Add `cache audit RUN_ID`:

```python
    if args[0] == "cache":
        _cache(args[1:])
        return
```

Implement:

```python
def _cache(args: tuple[str, ...]) -> None:
    if not args or args[0] != "audit":
        raise click.UsageError("cache requires subcommand: audit")
    if len(args) < 2:
        raise click.UsageError("cache audit requires run_id")
    from quantbench.api import run_reader
    from quantbench.data.retention import audit_run_data_slices

    report = audit_run_data_slices(run_reader.run_dir_for(args[1]))
    click.echo(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "ok":
        raise click.ClickException(f"data retention audit status: {report['status']}")
```

- [ ] **Step 4: Add launch limitation text**

README:

```markdown
Rerun reproducibility depends on retained cache slices. `manifest.json` records slice hashes, and `quantbench cache audit <run_id>` fails loudly if cached inputs are missing or drifted.
```

- [ ] **Step 5: Verify retention tests**

Run:

```bash
uv run pytest tests/test_data_retention.py tests/test_cli_e2e.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantbench/data/retention.py quantbench/cli.py README.md tests/test_data_retention.py
git commit -m "feat: audit retained data slices for rerun safety"
```

## Task 6: Add Perpetual Data Schema For Open Interest Readiness

**Files:**
- Create: `quantbench/data/perpetual.py`
- Modify: `quantbench/data/providers/base.py`
- Modify: `README.md`
- Test: `tests/test_phase5_crypto_universe.py`

- [ ] **Step 1: Write schema test**

Add:

```python
def test_perpetual_data_schema_accepts_optional_open_interest():
    from quantbench.data.perpetual import PerpetualData

    data = PerpetualData(
        symbol="BTC/USDT",
        timestamp="2026-07-04T00:00:00+00:00",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=123.0,
        funding_rate=0.0001,
        open_interest=None,
    )

    assert data.open_interest is None
    assert data.to_row()["funding_rate"] == 0.0001
```

Run:

```bash
uv run pytest tests/test_phase5_crypto_universe.py::test_perpetual_data_schema_accepts_optional_open_interest -q
```

Expected: FAIL because schema does not exist.

- [ ] **Step 2: Implement schema**

Create `quantbench/data/perpetual.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PerpetualData:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    funding_rate: float | None = None
    open_interest: float | None = None

    def to_row(self) -> dict:
        return asdict(self)
```

- [ ] **Step 3: Document scope**

README:

```markdown
Perpetual data schema now reserves `funding_rate` and `open_interest`; current launch fetches and models funding, while open interest is schema-ready but not yet fetched by the built-in CCXT provider.
```

- [ ] **Step 4: Verify schema test**

Run:

```bash
uv run pytest tests/test_phase5_crypto_universe.py::test_perpetual_data_schema_accepts_optional_open_interest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quantbench/data/perpetual.py README.md tests/test_phase5_crypto_universe.py
git commit -m "feat: add perpetual data schema with open interest slot"
```

## Task 7: Make Single-Asset Export Limitation Explicit

**Files:**
- Modify: `quantbench/factors/signal_export.py`
- Modify: `quantbench/cli.py`
- Modify: `README.md`
- Test: `tests/test_signal_export.py`

- [ ] **Step 1: Add export limitation test**

Add to `tests/test_signal_export.py`:

```python
def test_single_asset_export_returns_structured_limitation(monkeypatch):
    from quantbench.factors.entry import FactorEntry
    from quantbench.factors.signal_export import build_signal_export

    monkeypatch.setattr("quantbench.factors.signal_export.refresh_and_recompute_weights", lambda run_id, conn=None: None)
    entry = FactorEntry(
        name="single_asset_momentum",
        family="momentum",
        asset_class="equity",
        code="def compute(df):\n    return df.close.pct_change()",
        parameters=[],
        source_run_id="run_single",
        source_verdict="PROMISING",
        source_metrics={"sharpe": 1.0},
        source_findings=[],
        lifecycle_state="research",
        saved_at="2026-07-04T00:00:00+00:00",
        notes="",
        saved_from_rejected=False,
    )

    payload = build_signal_export(entry)

    assert payload["supported"] is False
    assert payload["limitation_code"] == "single_asset_export_not_supported"
```

Run:

```bash
uv run pytest tests/test_signal_export.py::test_single_asset_export_returns_structured_limitation -q
```

Expected: FAIL because current payload has only `"error"`.

- [ ] **Step 2: Update export payload**

In `signal_export.py`, replace the unsupported return with:

```python
return {
    "supported": False,
    "limitation_code": "single_asset_export_not_supported",
    "error": (
        f"signal export is not supported for factor {entry.name!r}: its source run "
        f"{entry.source_run_id!r} is not a cross-sectional run. Single-asset signal export is a documented launch limitation."
    ),
    "factor_name": entry.name,
    "source_run_id": entry.source_run_id,
    "source_verdict": entry.source_verdict,
}
```

For supported exports, add:

```python
"supported": True,
"risk_disclaimer": "Research signal export is not an order or investment recommendation.",
```

- [ ] **Step 3: Update CLI output**

In `_factor export`, when `"supported" is False`, raise:

```python
raise click.ClickException(payload["error"])
```

For JSON output, print the full structured payload unchanged.

- [ ] **Step 4: Add README limitation**

```markdown
`factor export` launch scope is cross-sectional factors only. Single-asset factor export returns a structured unsupported payload instead of pretending there is a universe-level target weight vector.
```

- [ ] **Step 5: Verify signal export tests**

Run:

```bash
uv run pytest tests/test_signal_export.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantbench/factors/signal_export.py quantbench/cli.py README.md tests/test_signal_export.py
git commit -m "fix: structure single asset export limitation"
```

## Task 8: Full Quant-Layer Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused quant tests**

```bash
uv run pytest tests/test_launch_trust_policy.py tests/test_crypto_universe_snapshot.py tests/test_llm_eval.py tests/test_data_retention.py tests/test_phase5_crypto_universe.py tests/test_signal_export.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Reviewer and golden tests**

```bash
uv run pytest tests/test_golden_run_discipline.py tests/test_phase10_golden_runs.py tests/test_phase105_statistics.py tests/test_phase12_reviewer.py -q
```

Expected: PASS. If `launch_trust_policy` adds warnings to golden cases, update the cases deliberately and document the verdict drift.

- [ ] **Step 3: Run full backend tests**

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run manual LLM eval only when API key is available**

```bash
uv run python -m quantbench eval llm --cases quantbench/evals/llm_cases.yaml
```

Expected: all cases PASS. This command may incur LLM cost and is not required for regular CI.

- [ ] **Step 5: Update launch readiness**

In `LAUNCH_READINESS.md` section 二:

- Mark equity launch positioning calibrated.
- Mark crypto PIT seed added.
- Mark LLM eval harness added.
- Mark data retention audit added.
- Mark PerpetualData schema and single-asset export limitation declared.

- [ ] **Step 6: Commit docs update**

```bash
git add LAUNCH_READINESS.md
git commit -m "docs: mark quant launch readiness gaps resolved"
```

## Acceptance Criteria

- Equity current-constituent runs are visibly demo-tier, not presented as equally launch-ready with crypto.
- Crypto runs can be launch-primary only when funding coverage is complete.
- New users can seed a minimal crypto PIT snapshot table locally.
- Manual LLM eval exists, is fake-client unit tested, and can run against the configured model on demand.
- Rerun reproducibility has an explicit cache retention audit.
- Perpetual schema reserves `funding_rate` and `open_interest`.
- Single-asset factor export returns a structured unsupported limitation, while cross-sectional export includes a risk disclaimer.
