# Launch Readiness Codex Blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清除 `LAUNCH_READINESS.md`「〇之二、第二轮审查（Codex）交叉验证的首发阻断项」中的 B1-B4，使公开首发不再依赖错误的 funding、开放的本地 API、乐观默认成交口径或不完整审查台。

**Architecture:** 以小模块收拢跨层不变量：`quantbench/engine/funding.py` 负责把原始 funding rows 对齐到持仓期；provider 只负责分页拉取，warehouse 只负责缓存与覆盖率元数据。API 安全面引入本地 token + origin allowlist，Web 文献导入改成上传文件而不是裸本地路径。执行假设改为保守默认 `open_t+1`，乐观 `close_t` 变成显式选择并进入 Reviewer warning；staging 改成 typed config，让执行、universe/date range、成本、borrow、中性化和分组数都可审改。

**Tech Stack:** Python 3.11+, pandas, DuckDB, ccxt, FastAPI, pydantic, pytest, React 19, TypeScript, Vite, Vitest, Playwright, GitHub Actions.

---

## Scope Map

| LAUNCH_READINESS item | Plan tasks |
|---|---|
| B1 funding 分页 + 持仓期对齐 | Task 1, Task 2, Task 3 |
| B2 CORS 全开 + 本地路径 ingest | Task 4, Task 5 |
| B3 默认 `close_t` 不保守 | Task 6 |
| B4 过期 funding 警告、审查台字段、文案漂移、CI | Task 3, Task 7, Task 8 |
| 架构建议 FundingSeries | Task 2 |
| 架构建议 ExecutionAssumption/StagingConfig | Task 6, Task 7 |

RunFinalizer 纯重构不纳入首发阻断修复。本计划不处理数据分片保留策略、Polygon 接入、bundle 分割或单次 run 成本预估。

## File Structure

- Create: `quantbench/engine/funding.py`
  - Owns funding period alignment, coverage accounting, and JSON-safe coverage serialization.
- Modify: `quantbench/data/providers/ccxt_perpetual.py`
  - Add paginated `fetch_funding_rate_history` loop.
- Modify: `quantbench/data/warehouse.py`
  - Preserve raw funding cache behavior and add funding coverage metadata in `fetch_universe_funding_rates`.
- Modify: `quantbench/engine/cross_sectional_backtest.py`
  - Replace exact timestamp `reindex` funding logic with `funding_cost_by_period`.
- Modify: `quantbench/agent/coordinator.py`, `quantbench/agent/tools/screening.py`
  - Carry funding coverage into config/review/warnings and use new execution default.
- Modify: `quantbench/agent/helpers/research_notes_support.py`, `quantbench/agent/constants.py`, `quantbench/skills/report.py`
  - Replace stale funding warning and stale execution default text.
- Create: `quantbench/api/security.py`
  - Centralize token validation and CORS origin configuration.
- Modify: `quantbench/api/server.py`, `quantbench/api/schemas.py`
  - Apply token dependency, restrict CORS, split literature arXiv ingest from upload ingest.
- Modify: `quantbench/literature/ingest.py`
  - Keep CLI local-path ingest; add explicit bytes/upload helper for Web/API.
- Modify: `web/src/api/client.ts`, `web/src/App.tsx`, `web/src/components/Sidebar.tsx`
  - Add token header support and file-upload paper import.
- Modify: `quantbench/engine/execution.py`, `quantbench/agent/helpers/config_normalizers.py`, `quantbench/agent/tools/backtest_single.py`
  - Change default fill to `open_t+1`; keep explicit `close_t` supported.
- Modify: `quantbench/review/report.py`
  - Add `execution_assumption` finding for explicit optimistic `close_t`.
- Create: `CHANGELOG.md`
  - Record funding and execution口径 breaking changes.
- Modify: `.github/workflows/tests.yml`
  - Add frontend build/lint/unit/e2e jobs.
- Modify tests:
  - `tests/test_phase11_remaining_data_foundation.py`
  - `tests/test_phase12_execution.py`
  - `tests/test_phase5_crypto_universe.py`
  - `tests/test_literature_api.py`
  - `tests/test_api.py`
  - `tests/test_phase13b_staging.py`
  - `tests/golden_run_registry.py`
  - `web/src/components/StagingReviewPanel.test.tsx`

## Task 1: Fix Funding Provider Pagination

**Files:**
- Modify: `quantbench/data/providers/ccxt_perpetual.py`
- Test: `tests/test_phase11_remaining_data_foundation.py`

- [ ] **Step 1: Add a failing pagination regression test**

Add this test next to `test_ccxt_funding_rate_history_normalizes_rows`:

```python
def test_ccxt_funding_rate_history_paginates_until_end(monkeypatch):
    from quantbench.data.providers import ccxt_perpetual

    eight_hours_ms = 8 * 60 * 60 * 1000
    calls = []

    class FakeExchange:
        def load_markets(self):
            return {"BTC/USDT": {"symbol": "BTC/USDT", "swap": True}}

        def parse8601(self, value):
            return int(pd.Timestamp(value).timestamp() * 1000)

        def fetch_funding_rate_history(self, symbol, since=None, limit=None):
            calls.append(since)
            if len(calls) == 1:
                return [
                    {"timestamp": since, "fundingRate": "0.01"},
                    {"timestamp": since + eight_hours_ms, "fundingRate": "0.02"},
                ]
            if len(calls) == 2:
                return [
                    {"timestamp": since, "fundingRate": "0.03"},
                    {"timestamp": since + eight_hours_ms, "fundingRate": "0.04"},
                ]
            return []

    monkeypatch.setattr(ccxt_perpetual, "_build_exchange", lambda: FakeExchange())

    result = ccxt_perpetual.fetch_funding_rate("BTC/USDT", "2024-01-01", "2024-01-03")

    assert len(calls) == 3
    assert result.df["funding_rate"].tolist() == [0.01, 0.02, 0.03, 0.04]
    assert calls[1] > calls[0]
```

Run:

```bash
uv run pytest tests/test_phase11_remaining_data_foundation.py::test_ccxt_funding_rate_history_paginates_until_end -q
```

Expected: FAIL because current code calls `fetch_funding_rate_history` once.

- [ ] **Step 2: Implement pagination in `fetch_funding_rate`**

Replace the single call with a bounded loop:

```python
end_ms = exchange.parse8601(f"{end}T00:00:00Z")
rows = []
while since < end_ms:
    batch = exchange.fetch_funding_rate_history(resolved_symbol, since=since, limit=1000)
    if not batch:
        break
    rows.extend(batch)
    timestamps = [int(item["timestamp"]) for item in batch if item.get("timestamp") is not None]
    if not timestamps:
        break
    last_ts = max(timestamps)
    next_since = last_ts + 1
    if next_since <= since:
        break
    since = next_since
    if last_ts >= end_ms:
        break
```

Keep the existing normalization and `< end_ts` filter.

- [ ] **Step 3: Verify provider pagination and existing funding tests**

Run:

```bash
uv run pytest tests/test_phase11_remaining_data_foundation.py::test_ccxt_funding_rate_history_normalizes_rows tests/test_phase11_remaining_data_foundation.py::test_ccxt_funding_rate_history_paginates_until_end -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add quantbench/data/providers/ccxt_perpetual.py tests/test_phase11_remaining_data_foundation.py
git commit -m "fix: paginate crypto funding history fetches"
```

## Task 2: Align Funding To Rebalance Periods

**Files:**
- Create: `quantbench/engine/funding.py`
- Modify: `quantbench/engine/cross_sectional_backtest.py`
- Test: `tests/test_phase11_remaining_data_foundation.py`

- [ ] **Step 1: Add failing tests for 8h funding rows inside a daily holding period**

Add two tests:

```python
def test_funding_cost_sums_all_rows_inside_rebalance_period():
    from quantbench.engine.funding import funding_cost_by_period

    weights = pd.DataFrame(
        {"BTC/USDT": [1.0]},
        index=pd.DatetimeIndex(["2024-01-01"], tz="UTC"),
    )
    funding = pd.DataFrame(
        {
            "symbol": ["BTC/USDT", "BTC/USDT", "BTC/USDT"],
            "timestamp": pd.to_datetime(
                ["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00"],
                utc=True,
            ),
            "funding_rate": [0.02, 0.02, 0.02],
        }
    )

    series = funding_cost_by_period(weights, funding)

    assert round(float(series.cost.iloc[0]), 6) == 0.06
    assert series.coverage["observed_period_symbol_pairs"] == 1
    assert series.coverage["missing_period_symbol_pairs"] == 0


def test_cross_sectional_backtest_subtracts_intraday_funding_rows():
    from quantbench.engine.cross_sectional_backtest import run_cross_sectional_backtest

    timestamps = pd.date_range("2024-01-01", periods=3, freq="1D", tz="UTC")
    rows = []
    for symbol, score in {"LONG": 2.0, "SHORT": 1.0}.items():
        for timestamp in timestamps:
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 1000.0,
                    "score": score,
                }
            )
    panel = pd.DataFrame(rows)
    funding = pd.DataFrame(
        {
            "symbol": ["LONG", "LONG", "LONG"],
            "timestamp": pd.to_datetime(
                ["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00"],
                utc=True,
            ),
            "funding_rate": [0.02, 0.02, 0.02],
        }
    )

    def compute(df):
        return df["score"]

    result = run_cross_sectional_backtest(panel, compute, n_groups=2, cost_bps=0, funding_rates=funding)

    assert result.metrics["funding_cost_total"] == 0.06
    assert round(float(result.returns.iloc[0]), 6) == -0.06
```

Run:

```bash
uv run pytest tests/test_phase11_remaining_data_foundation.py::test_funding_cost_sums_all_rows_inside_rebalance_period tests/test_phase11_remaining_data_foundation.py::test_cross_sectional_backtest_subtracts_intraday_funding_rows -q
```

Expected: FAIL because `_funding_cost` currently drops 08:00 and 16:00 rows by exact daily reindex.

- [ ] **Step 2: Create `quantbench/engine/funding.py`**

Public contract:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class FundingPeriodSeries:
    cost: pd.Series
    coverage: dict[str, Any]


def funding_cost_by_period(weights: pd.DataFrame, funding_rates: pd.DataFrame | None) -> FundingPeriodSeries:
    """Return signed funding carry by rebalance period.

    Funding rows are assigned to the holding interval [weight_timestamp, next_weight_timestamp).
    Positive weight * positive funding is a cost; negative weight * positive funding is a rebate.
    """
    if weights.empty:
        return FundingPeriodSeries(pd.Series(dtype="float64", index=weights.index), _empty_coverage(weights))
    if funding_rates is None or funding_rates.empty:
        return FundingPeriodSeries(pd.Series(0.0, index=weights.index), _empty_coverage(weights))

    required = {"timestamp", "symbol", "funding_rate"}
    missing = required - set(funding_rates.columns)
    if missing:
        raise ValueError("funding_rates must contain timestamp, symbol, and funding_rate columns")

    normalized = funding_rates.loc[:, ["timestamp", "symbol", "funding_rate"]].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    normalized["symbol"] = normalized["symbol"].astype(str)
    normalized["funding_rate"] = pd.to_numeric(normalized["funding_rate"], errors="coerce")
    normalized = normalized.dropna(subset=["timestamp", "symbol", "funding_rate"]).sort_values("timestamp")

    index = pd.DatetimeIndex(pd.to_datetime(weights.index, utc=True))
    columns = [str(column) for column in weights.columns]
    safe_weights = weights.copy()
    safe_weights.index = index
    safe_weights.columns = columns

    if len(index) >= 2:
        period_delta = pd.Series(index[1:] - index[:-1]).median()
    else:
        period_delta = pd.Timedelta(days=1)

    values: dict[pd.Timestamp, float] = {}
    observed_pairs: set[tuple[pd.Timestamp, str]] = set()
    aligned_rows = 0

    for position, start in enumerate(index):
        end = index[position + 1] if position + 1 < len(index) else start + period_delta
        window = normalized[(normalized["timestamp"] >= start) & (normalized["timestamp"] < end)]
        if window.empty:
            values[start] = 0.0
            continue
        period_rates = window.pivot_table(columns="symbol", values="funding_rate", aggfunc="sum").reindex(columns=columns, fill_value=0)
        row = period_rates.iloc[0]
        values[start] = float((safe_weights.loc[start] * row).sum())
        aligned_rows += len(window)
        for symbol in set(window["symbol"].astype(str)) & set(columns):
            observed_pairs.add((start, symbol))

    expected_pairs = len(index) * len(columns)
    missing_pairs = max(expected_pairs - len(observed_pairs), 0)
    coverage = {
        "raw_rows": int(len(normalized)),
        "aligned_rows": int(aligned_rows),
        "expected_period_symbol_pairs": int(expected_pairs),
        "observed_period_symbol_pairs": int(len(observed_pairs)),
        "missing_period_symbol_pairs": int(missing_pairs),
        "coverage_ratio": round(len(observed_pairs) / expected_pairs, 6) if expected_pairs else 1.0,
    }
    return FundingPeriodSeries(pd.Series(values).reindex(index).fillna(0.0), coverage)


def _empty_coverage(weights: pd.DataFrame) -> dict[str, Any]:
    expected_pairs = len(weights.index) * len(weights.columns)
    return {
        "raw_rows": 0,
        "aligned_rows": 0,
        "expected_period_symbol_pairs": int(expected_pairs),
        "observed_period_symbol_pairs": 0,
        "missing_period_symbol_pairs": int(expected_pairs),
        "coverage_ratio": 0.0 if expected_pairs else 1.0,
    }
```

- [ ] **Step 3: Wire cross-sectional engine through the new module**

In `quantbench/engine/cross_sectional_backtest.py`:

```python
from quantbench.engine.funding import funding_cost_by_period
```

Replace `_funding_cost(weights, funding_rates)` body with:

```python
return funding_cost_by_period(weights, funding_rates).cost
```

If the result object needs coverage in Task 3, extend `CrossSectionalBacktestResult` there rather than mixing metadata into this step.

- [ ] **Step 4: Verify funding alignment tests**

Run:

```bash
uv run pytest tests/test_phase11_remaining_data_foundation.py -q
```

Expected: PASS, including existing directionality assertions.

- [ ] **Step 5: Commit**

```bash
git add quantbench/engine/funding.py quantbench/engine/cross_sectional_backtest.py tests/test_phase11_remaining_data_foundation.py
git commit -m "fix: align funding rates to rebalance periods"
```

## Task 3: Surface Funding Coverage And Replace The Stale Warning

**Files:**
- Modify: `quantbench/data/warehouse.py`
- Modify: `quantbench/engine/cross_sectional_backtest.py`
- Modify: `quantbench/agent/coordinator.py`
- Modify: `quantbench/agent/tools/screening.py`
- Modify: `quantbench/agent/helpers/research_notes_support.py`
- Modify: `quantbench/agent/constants.py`
- Test: `tests/test_phase5_crypto_universe.py`
- Test: `tests/test_phase11_remaining_data_foundation.py`

- [ ] **Step 1: Add tests proving the old warning disappears when funding is modeled and complete**

Change `test_cross_sectional_crypto_uses_btc_benchmark_and_writes_funding_warning` into two tests:

1. A complete funding case:
   - Monkeypatch `fetch_universe_funding_rates` to return three rows per day for both symbols and meta `{"coverage": {"coverage_ratio": 1.0, "missing_period_symbol_pairs": 0}, "failed": {}}`.
   - Assert no warning contains `"do not model funding rate carry cost"`.
   - Assert manifest config has `funding.coverage.coverage_ratio == 1.0`.

2. An incomplete funding case:
   - Monkeypatch `fetch_universe_funding_rates` to return empty rows and meta `{"coverage": {"coverage_ratio": 0.0, "missing_period_symbol_pairs": 10}, "failed": {"BTC/USDT": "RateLimitExceeded"}}`.
   - Assert the warning says funding coverage is incomplete and includes the coverage ratio.

Run:

```bash
uv run pytest tests/test_phase5_crypto_universe.py::test_cross_sectional_crypto_complete_funding_does_not_emit_stale_warning tests/test_phase5_crypto_universe.py::test_cross_sectional_crypto_incomplete_funding_emits_coverage_warning -q
```

Expected: FAIL until warning logic is conditional.

- [ ] **Step 2: Add coverage metadata to `fetch_universe_funding_rates`**

Return meta shape:

```python
{
    "symbols_requested": len(universe.symbols),
    "symbols_fetched": fetched,
    "failed": failed,
    "sources": sources,
    "coverage": {
        "start": start,
        "end": end,
        "symbols": len(universe.symbols),
        "raw_rows": len(panel),
        "symbols_with_rows": int(panel["symbol"].nunique()) if not panel.empty else 0,
        "missing_symbols": sorted(set(universe.symbols) - set(panel["symbol"].astype(str))) if not panel.empty else sorted(universe.symbols),
        "failed_symbols": sorted(failed),
    },
}
```

Do not estimate period completeness here; raw fetch coverage is separate from engine alignment coverage.

- [ ] **Step 3: Attach alignment coverage after backtest**

Extend `CrossSectionalBacktestResult` with:

```python
funding_coverage: dict[str, Any]
```

In `run_cross_sectional_backtest`, compute:

```python
funding_series = funding_cost_by_period(weights, funding_rates)
funding_cost = funding_series.cost.reindex(long_short.index).fillna(0)
```

Pass `funding_series.coverage` into the result and include it in `to_json_dict()`:

```python
"funding_coverage": self.funding_coverage,
```

- [ ] **Step 4: Merge funding coverage into coordinator meta**

After each cross-sectional backtest:

```python
if funding_meta is not None:
    funding_meta = {**funding_meta, "alignment": backtest.funding_coverage}
    ctx.funding_meta = funding_meta
```

Do the same in screening child config and summary payload.

- [ ] **Step 5: Replace the constant warning with conditional warnings**

In `quantbench/agent/constants.py`, replace `CRYPTO_PERPETUAL_FUNDING_WARNING` with:

```python
CRYPTO_PERPETUAL_FUNDING_COVERAGE_WARNING = (
    "Crypto perpetual funding coverage is incomplete; funding-adjusted PnL may still be biased."
)
```

In `research_notes_support.py`, replace `_append_crypto_perpetual_warning` with:

```python
def _append_crypto_perpetual_warning(ctx: _RunContext) -> list[str]:
    meta = ctx.funding_meta or {}
    alignment = meta.get("alignment") if isinstance(meta, dict) else {}
    failed = meta.get("failed") if isinstance(meta, dict) else {}
    ratio = float((alignment or {}).get("coverage_ratio", 0.0) or 0.0)
    missing_pairs = int((alignment or {}).get("missing_period_symbol_pairs", 0) or 0)
    if ratio >= 0.98 and missing_pairs == 0 and not failed:
        return []
    warning = (
        f"{CRYPTO_PERPETUAL_FUNDING_COVERAGE_WARNING} "
        f"Aligned funding coverage={ratio:.1%}; missing period-symbol pairs={missing_pairs}; "
        f"failed symbols={len(failed or {})}."
    )
    if warning not in ctx.warnings:
        ctx.warnings.append(warning)
        return [warning]
    return []
```

- [ ] **Step 6: Verify funding warning behavior**

Run:

```bash
uv run pytest tests/test_phase5_crypto_universe.py tests/test_phase11_remaining_data_foundation.py -q
```

Expected: PASS and no assertion references the stale phrase `"do not model funding rate carry cost"`.

- [ ] **Step 7: Commit**

```bash
git add quantbench/data/warehouse.py quantbench/engine/cross_sectional_backtest.py quantbench/agent/coordinator.py quantbench/agent/tools/screening.py quantbench/agent/helpers/research_notes_support.py quantbench/agent/constants.py tests/test_phase5_crypto_universe.py tests/test_phase11_remaining_data_foundation.py
git commit -m "fix: report funding coverage instead of stale no-funding warning"
```

## Task 4: Lock Down Local API With Token And CORS Allowlist

**Files:**
- Create: `quantbench/api/security.py`
- Modify: `quantbench/api/server.py`
- Modify: `web/src/api/client.ts`
- Test: `tests/test_api.py`
- Test: `tests/test_literature_api.py`

- [ ] **Step 1: Add failing API security tests**

Add tests in `tests/test_api.py`:

```python
def test_protected_api_requires_local_token(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTBENCH_API_TOKEN", "test-token")
    monkeypatch.setattr("quantbench.api.run_reader.RUNS_DIR", tmp_path)
    from quantbench.api.server import app

    client = TestClient(app)

    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"X-QuantBench-Token": "test-token"}).status_code == 200


def test_cors_rejects_untrusted_origins(monkeypatch):
    monkeypatch.setenv("QUANTBENCH_API_TOKEN", "test-token")
    from quantbench.api.server import app

    client = TestClient(app)
    response = client.options(
        "/api/runs",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-QuantBench-Token",
        },
    )

    assert response.status_code in (400, 405)
    assert response.headers.get("access-control-allow-origin") != "https://attacker.example"
```

Run:

```bash
uv run pytest tests/test_api.py::test_protected_api_requires_local_token tests/test_api.py::test_cors_rejects_untrusted_origins -q
```

Expected: FAIL because there is no token dependency and CORS is `*`.

- [ ] **Step 2: Create `quantbench/api/security.py`**

Implement:

```python
from __future__ import annotations

import os
from secrets import compare_digest

from fastapi import Header, HTTPException


TOKEN_ENV = "QUANTBENCH_API_TOKEN"
ORIGINS_ENV = "QUANTBENCH_ALLOWED_ORIGINS"
DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def allowed_origins() -> list[str]:
    raw = os.environ.get(ORIGINS_ENV)
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return list(DEFAULT_ALLOWED_ORIGINS)


def configured_token() -> str:
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise HTTPException(status_code=500, detail=f"{TOKEN_ENV} is required before starting the API")
    return token


def require_api_token(x_quantbench_token: str | None = Header(default=None)) -> None:
    expected = configured_token()
    if not x_quantbench_token or not compare_digest(x_quantbench_token, expected):
        raise HTTPException(status_code=401, detail="missing or invalid QuantBench API token")
```

- [ ] **Step 3: Apply CORS allowlist and token dependency**

In `server.py`:

```python
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from quantbench.api.security import allowed_origins, require_api_token
```

Change CORS:

```python
allow_origins=allowed_origins(),
allow_methods=["GET", "POST", "OPTIONS"],
allow_headers=["Content-Type", "X-QuantBench-Token"],
```

Add `dependencies=[Depends(require_api_token)]` to every `/api/*` route decorator, or define a router with the dependency and move existing endpoints onto that router. Keep tests explicit by passing the header in fixtures.

- [ ] **Step 4: Update test fixtures with token headers**

For each `TestClient(app)` fixture in `tests/test_api.py` and `tests/test_literature_api.py`:

```python
monkeypatch.setenv("QUANTBENCH_API_TOKEN", "test-token")
return TestClient(app, headers={"X-QuantBench-Token": "test-token"})
```

- [ ] **Step 5: Add token header support to the Web client**

In `web/src/api/client.ts`:

```ts
const apiToken = import.meta.env.VITE_QUANTBENCH_API_TOKEN as string | undefined;

function authHeaders(extra?: HeadersInit): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(apiToken ? { "X-QuantBench-Token": apiToken } : {}),
    ...(extra ?? {}),
  };
}
```

Use `authHeaders()` in `request()` and direct `fetch()` calls.

- [ ] **Step 6: Verify API tests**

Run:

```bash
uv run pytest tests/test_api.py tests/test_literature_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add quantbench/api/security.py quantbench/api/server.py web/src/api/client.ts tests/test_api.py tests/test_literature_api.py
git commit -m "fix: require local API token and restrict CORS"
```

## Task 5: Replace Web Local-Path Literature Ingest With File Upload

**Files:**
- Modify: `quantbench/api/server.py`
- Modify: `quantbench/api/schemas.py`
- Modify: `quantbench/literature/ingest.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/Sidebar.tsx`
- Test: `tests/test_literature_api.py`

- [ ] **Step 1: Add failing API tests**

Add:

```python
def test_web_json_ingest_rejects_local_paths(tmp_path, client):
    pdf = tmp_path / "secret.pdf"
    pdf.write_bytes(make_text_pdf([["Secret", "Local content"]]))

    response = client.post("/api/literature/ingest", json={"source": str(pdf)})

    assert response.status_code == 400
    assert "upload" in response.text.lower()


def test_upload_ingest_accepts_pdf_bytes(client):
    response = client.post(
        "/api/literature/ingest/upload",
        files={"file": ("paper.pdf", make_text_pdf([["Momentum Paper", "12-1 signal"]]), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Momentum Paper"
```

Run:

```bash
uv run pytest tests/test_literature_api.py::test_web_json_ingest_rejects_local_paths tests/test_literature_api.py::test_upload_ingest_accepts_pdf_bytes -q
```

Expected: FAIL until upload endpoint exists and JSON path ingest is restricted.

- [ ] **Step 2: Add upload helper in `literature/ingest.py`**

Add:

```python
def ingest_upload_with_bytes(filename: str, pdf_bytes: bytes) -> tuple[Paper, bytes]:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("uploaded literature file must be a PDF")
    paper = ingest_pdf_bytes(pdf_bytes, source=filename, source_kind="upload")
    return paper, pdf_bytes
```

Keep `ingest_pdf_with_bytes(path)` for CLI only.

- [ ] **Step 3: Restrict JSON ingest to arXiv**

In `server.py` JSON endpoint:

```python
if not is_arxiv_reference(source):
    raise HTTPException(status_code=400, detail="Local PDFs must be imported with the upload endpoint.")
```

Then call `ingest_arxiv_with_bytes`.

- [ ] **Step 4: Add upload endpoint**

```python
@app.post("/api/literature/ingest/upload", response_model=PaperSummary, dependencies=[Depends(require_api_token)])
async def upload_paper(file: UploadFile = File(...)) -> PaperSummary:
    from quantbench.literature.ingest import ingest_upload_with_bytes

    pdf_bytes = await file.read()
    try:
        paper, raw_pdf = ingest_upload_with_bytes(file.filename or "upload.pdf", pdf_bytes)
        _paper_store().save(paper, pdf_bytes=raw_pdf)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return PaperSummary(**paper.metadata_dict())
```

- [ ] **Step 5: Update Web import flow**

In `client.ts`:

```ts
export function ingestPaperSource(source: string): Promise<PaperSummary> {
  return request<PaperSummary>("/literature/ingest", {
    method: "POST",
    body: JSON.stringify({ source }),
  });
}

export async function uploadPaper(file: File): Promise<PaperSummary> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/literature/ingest/upload", {
    method: "POST",
    headers: apiToken ? { "X-QuantBench-Token": apiToken } : undefined,
    body,
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  return response.json() as Promise<PaperSummary>;
}
```

In `Sidebar.tsx`, add a file input next to arXiv input and remove the local path placeholder. The visible placeholder should become `arXiv URL / ID`; local PDFs are selected via file input.

- [ ] **Step 6: Verify literature tests**

Run:

```bash
uv run pytest tests/test_literature_api.py tests/test_literature_ingest.py -q
```

Expected: PASS. CLI path ingest tests remain valid because CLI still calls `ingest_and_store`.

- [ ] **Step 7: Commit**

```bash
git add quantbench/api/server.py quantbench/api/schemas.py quantbench/literature/ingest.py web/src/api/client.ts web/src/App.tsx web/src/components/Sidebar.tsx tests/test_literature_api.py
git commit -m "fix: upload local literature PDFs instead of accepting paths"
```

## Task 6: Change Default Execution To `open_t+1` And Warn On Explicit `close_t`

**Files:**
- Modify: `quantbench/engine/execution.py`
- Modify: `quantbench/agent/helpers/config_normalizers.py`
- Modify: `quantbench/agent/constants.py`
- Modify: `quantbench/agent/tools/backtest_single.py`
- Modify: `quantbench/agent/coordinator.py`
- Modify: `quantbench/agent/tools/screening.py`
- Modify: `quantbench/review/report.py`
- Modify: `quantbench/skills/report.py`
- Modify: `tests/test_phase12_execution.py`
- Modify: `tests/golden_run_registry.py`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Add failing default-execution tests**

Add:

```python
def test_execution_config_defaults_to_open_next():
    from quantbench.engine.execution import ExecutionConfig

    assert ExecutionConfig().fill_price == "open_t+1"


def test_review_warns_when_close_t_is_explicitly_selected():
    from quantbench.review.report import run_review

    index = pd.date_range("2024-01-01", periods=80, freq="1D", tz="UTC")
    returns = pd.Series([0.001] * len(index), index=index)
    data = pd.DataFrame({"timestamp": index, "close": 100.0})

    report = run_review(
        code="def compute(df):\n    return df['close'].pct_change().fillna(0.0)\n",
        returns=returns,
        cost_bps=0,
        rerun_at_cost=lambda bps: {"sharpe": 1.0},
        rerun_with_code=lambda candidate: {"sharpe": 1.0},
        out_of_sample_data=data,
        run_on_data=lambda frame: {"sharpe": 1.0},
        execution={"signal_time": "close_t", "fill_price": "close_t"},
    )

    finding = next(item for item in report.findings if item.check == "execution_assumption")
    assert finding.severity == "warning"
```

Run:

```bash
uv run pytest tests/test_phase12_execution.py::test_execution_config_defaults_to_open_next tests/test_phase12_execution.py::test_review_warns_when_close_t_is_explicitly_selected -q
```

Expected: FAIL until defaults and Reviewer are updated.

- [ ] **Step 2: Change execution defaults**

In `ExecutionConfig`:

```python
signal_time: str = "close_t"
fill_price: str = "open_t+1"
```

In `_execution_config`:

```python
fill_price=str(execution.get("fill_price") or "open_t+1")
```

Keep explicit `ExecutionConfig(fill_price="close_t")` behavior unchanged.

- [ ] **Step 3: Add Reviewer execution-assumption finding**

In `run_review`, add parameter:

```python
execution: dict[str, Any] | None = None,
```

Append:

```python
findings.append(_execution_assumption_finding(execution))
```

Implement:

```python
def _execution_assumption_finding(execution: dict[str, Any] | None) -> ReviewFinding:
    fill_price = str((execution or {}).get("fill_price") or "open_t+1")
    detail = {"fill_price": fill_price, "signal_time": str((execution or {}).get("signal_time") or "close_t")}
    if fill_price == "close_t":
        return ReviewFinding(
            "execution_assumption",
            "warning",
            "Backtest uses optimistic close_t fills; signals formed at close_t are assumed executable at that same close.",
            detail,
        )
    if fill_price == "open_t+1":
        return ReviewFinding("execution_assumption", "pass", "Backtest uses next-open fills after close_t signal formation.", detail)
    return ReviewFinding("execution_assumption", "info", f"Backtest uses explicit fill assumption {fill_price}.", detail)
```

- [ ] **Step 4: Pass execution into every `run_review` call**

Use `execution_config.to_dict()` or `execution.to_dict()` in:

- `quantbench/agent/tools/backtest_single.py`
- `quantbench/agent/coordinator.py`
- `quantbench/agent/tools/screening.py`
- `tests/golden_run_registry.py` direct `run_review` calls

- [ ] **Step 5: Update schema and note text**

In `constants.py`, replace all `"Default close_t"` descriptions with:

```python
"Default open_t+1. Use close_t only as an explicitly optimistic diagnostic convention."
```

In `skills/report.py`, replace fallback:

```python
execution.get("fill_price", "open_t+1")
```

- [ ] **Step 6: Update golden registry deliberately**

Run:

```bash
uv run pytest tests/test_golden_run_discipline.py -q
```

If verdicts drift only because `execution_assumption` adds a warning, update `expected_verdicts` to the new intended buckets and add required finding:

```python
required_findings={"execution_assumption": "pass", "lookahead": "critical"}
```

For cases intentionally using `close_t`, set explicit `execution={"signal_time": "close_t", "fill_price": "close_t"}` and required finding `{"execution_assumption": "warning"}`.

- [ ] **Step 7: Add `CHANGELOG.md`**

Content:

```markdown
# Changelog

## Unreleased

- Changed default execution fill from `close_t` to `open_t+1`.
- Explicit `close_t` runs now receive a Reviewer warning because same-close fills are optimistic.
- Fixed crypto perpetual funding cost estimation: funding history is paginated and intraday funding rows are aggregated into rebalance holding periods.
```

- [ ] **Step 8: Verify execution and golden tests**

Run:

```bash
uv run pytest tests/test_phase12_execution.py tests/test_golden_run_discipline.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add quantbench/engine/execution.py quantbench/agent/helpers/config_normalizers.py quantbench/agent/constants.py quantbench/agent/tools/backtest_single.py quantbench/agent/coordinator.py quantbench/agent/tools/screening.py quantbench/review/report.py quantbench/skills/report.py tests/test_phase12_execution.py tests/golden_run_registry.py CHANGELOG.md
git commit -m "fix: default to next-open execution and warn on close fills"
```

## Task 7: Expand Staging Review To Typed Execution And Research Config

**Files:**
- Modify: `quantbench/agent/staging.py`
- Modify: `quantbench/agent/coordinator.py`
- Modify: `quantbench/agent/tools/backtest_single.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/components/StagingReviewPanel.tsx`
- Test: `tests/test_phase13b_staging.py`
- Create: `web/src/components/StagingReviewPanel.test.tsx`

- [ ] **Step 1: Add backend tests for nested config overrides**

Add:

```python
def test_staging_overrides_preserve_nested_research_config():
    from quantbench.agent.staging import apply_staging_overrides

    code = "def compute(df):\n    return df['close'].pct_change().fillna(0)\n"
    config = {
        "start": "2024-01-01",
        "end": "2024-03-01",
        "timeframe": "1d",
        "n_groups": 10,
        "cost_bps": 5,
        "execution": {"signal_time": "close_t", "fill_price": "open_t+1"},
        "liquidity_cost": {"enabled": False, "aum_usd": 1000000, "participation_cap": 0.02},
        "borrow_cost": {"enabled": False},
        "neutralize": [],
        "universe": {"name": "sp500", "as_of_date": "2024-03-01", "point_in_time": False, "limit": 50},
    }
    overrides = {
        "config": {
            "n_groups": 5,
            "execution": {"signal_time": "close_t", "fill_price": "close_t"},
            "neutralize": ["beta", "size"],
            "borrow_cost": {"enabled": True},
        }
    }

    _, final_config = apply_staging_overrides(code, config, overrides)

    assert final_config["n_groups"] == 5
    assert final_config["execution"]["fill_price"] == "close_t"
    assert final_config["neutralize"] == ["beta", "size"]
    assert final_config["borrow_cost"] == {"enabled": True}
```

Run:

```bash
uv run pytest tests/test_phase13b_staging.py::test_staging_overrides_preserve_nested_research_config -q
```

Expected: PASS with current shallow merge for this exact shape, but this locks the contract before UI expansion.

- [ ] **Step 2: Include full editable config in staging artifacts**

In cross-sectional coordinator config passed to `StagingGate.review`, include:

```python
"universe": {
    "name": ctx.universe.name,
    "as_of_date": ctx.universe.as_of_date,
    "point_in_time": ctx.universe.point_in_time,
    "limit": ctx.universe.sample_limit,
},
"start": start,
"end": end,
"timeframe": timeframe,
"n_groups": n_groups,
"cost_bps": cost_bps,
"execution": execution or {"signal_time": "close_t", "fill_price": "open_t+1"},
"liquidity_cost": liquidity_cost or {"enabled": False},
"borrow_cost": borrow_cost or {"enabled": False},
"neutralize": neutralize or [],
```

In `StagingGate.review`, add this config to artifact:

```python
"config": original_config,
```

- [ ] **Step 3: Re-fetch data when staging changes data-shaping fields**

After staging returns in `build_run_cross_sectional_backtest_skill`, compare original and final values for:

```python
DATA_SHAPING_KEYS = {"universe", "start", "end", "timeframe"}
```

If changed:

1. Rebuild universe from `staged.config["universe"]`.
2. Re-fetch OHLCV and funding.
3. Re-run `run_signal_code_panel(code, panel)`.
4. Re-run `build_validation_report` and save the second validation report under `ctx.staging["post_override_validation_report"]`.

This prevents a user-edited date range/universe from being recorded in config while the old panel is still used.

- [ ] **Step 4: Add typed frontend config**

In `types.ts`:

```ts
export interface StagingConfig {
  start?: string;
  end?: string;
  timeframe?: string;
  n_groups?: number;
  cost_bps?: number;
  execution?: { signal_time?: string; fill_price?: "open_t+1" | "close_t" | "close_t+1" };
  liquidity_cost?: { enabled?: boolean; aum_usd?: number; participation_cap?: number };
  borrow_cost?: { enabled?: boolean };
  neutralize?: string[];
  universe?: { name?: string; as_of_date?: string; point_in_time?: boolean; limit?: number | null };
}
```

Extend `StagingArtifact` with `config?: StagingConfig`.

- [ ] **Step 5: Replace the single `cost_bps` input with typed controls**

In `StagingReviewPanel.tsx`, maintain:

```ts
const [configDraft, setConfigDraft] = useState<StagingConfig>(artifact.config ?? {});
```

Submit:

```ts
const overrides: Record<string, unknown> = { config: configDraft };
if (code !== initialCode) overrides.code = code;
```

Controls required before launch:

- `execution.fill_price`: select with `open_t+1`, `close_t+1`, `close_t`
- `start`, `end`: date inputs
- `timeframe`: text input
- `universe.name`, `universe.as_of_date`, `universe.limit`, `universe.point_in_time`
- `n_groups`, `cost_bps`
- `liquidity_cost.enabled`, `liquidity_cost.aum_usd`, `liquidity_cost.participation_cap`
- `borrow_cost.enabled`
- `neutralize`: checkboxes for `beta`, `size`, `sector`

- [ ] **Step 6: Add frontend test**

Create `web/src/components/StagingReviewPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StagingReviewPanel } from "./StagingReviewPanel";

describe("StagingReviewPanel", () => {
  it("submits typed config overrides", async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(
      <StagingReviewPanel
        isAwaiting={true}
        onConfirm={onConfirm}
        artifact={{
          factor_spec: { code: "def compute(df):\n    return df.close", formula: "df.close" },
          config: {
            cost_bps: 5,
            n_groups: 10,
            execution: { signal_time: "close_t", fill_price: "open_t+1" },
            neutralize: [],
          },
          validation_report: { lookahead_issues: [], has_shift: false, nan_ratio: 0, coverage_ratio: 1, output_aligned: true },
          gate_decision: { decision: "stopped", risk_score: 1, cost_score: 0, reasons: ["no_shift_detected"] },
        }}
      />,
    );

    await userEvent.selectOptions(screen.getByLabelText("Fill price"), "close_t");
    await userEvent.clear(screen.getByLabelText("Groups"));
    await userEvent.type(screen.getByLabelText("Groups"), "5");
    await userEvent.click(screen.getByLabelText("Neutralize beta"));
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        config: expect.objectContaining({
          n_groups: 5,
          execution: expect.objectContaining({ fill_price: "close_t" }),
          neutralize: ["beta"],
        }),
      }),
    );
  });
});
```

- [ ] **Step 7: Verify staging tests**

Run:

```bash
uv run pytest tests/test_phase13b_staging.py -q
cd web && npm test -- StagingReviewPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add quantbench/agent/staging.py quantbench/agent/coordinator.py quantbench/agent/tools/backtest_single.py web/src/types.ts web/src/components/StagingReviewPanel.tsx web/src/components/StagingReviewPanel.test.tsx tests/test_phase13b_staging.py
git commit -m "feat: expand staging review to typed research config"
```

## Task 8: Clean Copy Drift And Add Frontend CI

**Files:**
- Modify: `web/src/components/ChatInput.tsx`
- Modify: `PROJECT_STATUS.md`
- Modify: `.github/workflows/tests.yml`
- Modify: `README.md`

- [ ] **Step 1: Remove false interaction promises from ChatInput**

Find the placeholder that mentions unavailable `@/#//⌘K` interactions and replace it with text that only promises current behavior:

```tsx
placeholder="Describe the factor, universe, and review you want to run..."
```

Run:

```bash
rg -n "@|#|⌘K|//" web/src/components/ChatInput.tsx
```

Expected: no placeholder claim for unavailable interactions.

- [ ] **Step 2: Update `PROJECT_STATUS.md` literature status**

Replace the stale “4.3 文献接入未做” claim with:

```markdown
4.3 文献接入已落地到 CLI/API/Web：支持 arXiv ingest、本地 PDF 上传/CLI ingest、paper viewer、selection-grounded QA、paper-to-run reproduce。安全修订后，Web/API 不再接受裸本地路径。
```

- [ ] **Step 3: Update README safety posture**

Add a section:

```markdown
## Local API Safety

QuantBench is a local single-user research tool. Start the API with `QUANTBENCH_API_TOKEN` set, keep it bound to localhost, and do not expose the port to a network. The web client sends `X-QuantBench-Token`; cross-origin browser access is restricted to configured localhost origins.
```

Update execution wording:

```markdown
The default execution convention is `open_t+1`. `close_t` remains available only as an explicitly optimistic diagnostic assumption and is flagged by Reviewer.
```

- [ ] **Step 4: Add frontend CI jobs**

In `.github/workflows/tests.yml`, keep Python job and add:

```yaml
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install frontend dependencies
        run: npm ci
      - name: Lint frontend
        run: npm run lint
      - name: Unit test frontend
        run: npm test
      - name: Build frontend
        run: npm run build

  frontend-e2e:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install frontend dependencies
        run: npm ci
      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium
      - name: Run Playwright
        run: npm run test:e2e
```

- [ ] **Step 5: Verify docs and frontend commands locally**

Run:

```bash
rg -n "4\\.3|do not model funding|Default close_t|⌘K|本地 PDF 路径" README.md PROJECT_STATUS.md web/src quantbench
cd web && npm run lint && npm test && npm run build
```

Expected: no stale copy; lint/test/build pass.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/ChatInput.tsx PROJECT_STATUS.md README.md .github/workflows/tests.yml
git commit -m "chore: clean launch copy drift and add frontend CI"
```

## Task 9: Full Launch-Blocker Verification

**Files:**
- No new files expected.
- Uses all touched files from Tasks 1-8.

- [ ] **Step 1: Run focused backend regression suite**

```bash
uv run pytest tests/test_phase11_remaining_data_foundation.py tests/test_phase12_execution.py tests/test_phase5_crypto_universe.py tests/test_literature_api.py tests/test_api.py tests/test_phase13b_staging.py tests/test_golden_run_discipline.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend suite**

```bash
uv run pytest -q
```

Expected: PASS. If failures are pure expectation drift from the intentional default execution change, update the test to assert the new default explicitly rather than weakening the assertion.

- [ ] **Step 3: Run frontend suite**

```bash
cd web && npm run lint && npm test && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run Playwright**

```bash
cd web && npm run test:e2e
```

Expected: PASS. If Playwright needs browsers locally, run `npx playwright install chromium` once and repeat.

- [ ] **Step 5: Manual exploit regression for B2**

With API started using `QUANTBENCH_API_TOKEN=manual-test-token`, verify:

```bash
curl -i http://127.0.0.1:8000/api/runs
curl -i -H "X-QuantBench-Token: manual-test-token" http://127.0.0.1:8000/api/runs
curl -i -X OPTIONS http://127.0.0.1:8000/api/literature/ingest \
  -H "Origin: https://attacker.example" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: X-QuantBench-Token"
```

Expected:

- First request: 401.
- Second request: 200.
- Preflight from attacker origin: no `access-control-allow-origin: https://attacker.example`.

- [ ] **Step 6: Manual B1 funding sanity**

Use a small synthetic call or monkeypatched script to confirm:

```python
from quantbench.engine.funding import funding_cost_by_period
```

For one daily long BTC weight and three 8h funding rows of `0.02`, expected cost is `0.06`, not `0.02`.

- [ ] **Step 7: Update `LAUNCH_READINESS.md` after implementation**

When all tasks pass, edit the original section:

- B1: mark fixed with commit hash and note affected historical crypto runs should be rerun or marked stale.
- B2: mark fixed with token/upload behavior.
- B3: mark fixed with `open_t+1` default and `CHANGELOG.md` entry.
- B4: mark fixed for funding warning, staging fields, copy drift, CI.

- [ ] **Step 8: Final commit**

```bash
git add LAUNCH_READINESS.md
git commit -m "docs: mark codex launch blockers resolved"
```

## Acceptance Criteria

- Funding fetch pagination covers multi-year 8h histories instead of one 1000-row page.
- Funding cost for daily crypto periods sums 00:00, 08:00, and 16:00 rows inside the holding interval.
- Crypto runs no longer claim funding is unmodeled when funding is modeled and complete.
- Incomplete funding coverage creates a concrete coverage warning with missing pair/failure counts.
- API no longer exposes local data to arbitrary origins and requires `X-QuantBench-Token`.
- Web/API local PDF ingest uses upload bytes; JSON ingest accepts arXiv only.
- Default execution is `open_t+1`.
- Explicit `close_t` fills produce a Reviewer warning and are visible in reports/config.
- Staging review can edit execution, universe, date range, liquidity, borrow, neutralization, and `n_groups`.
- Frontend lint/unit/build/e2e are in CI.
- Full backend and frontend suites pass.
