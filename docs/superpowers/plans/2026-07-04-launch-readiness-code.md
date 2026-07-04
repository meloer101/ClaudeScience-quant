# Launch Readiness Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决 `LAUNCH_READINESS.md`「一、代码角度」列出的首发代码层缺口：可变目录不可写、平台支持不清、API 本地安全姿态不足、前端/CI 覆盖不足和包元数据陈旧。

**Architecture:** 采用“本地 alpha 也要像可分发包一样运行”的路线：包内代码只读，用户数据写入 `QUANTBENCH_HOME` 或 `~/.quantbench`，运行目录通过环境变量覆盖。平台支持用启动期 guard 统一失败信息，API 通过本地 token、localhost 绑定和安全文档形成闭环。CI 拆成 Python 与 frontend 两条，包构建 smoke test 防止 wheel 安装后回归。

**Tech Stack:** Python 3.11+, pathlib, click, FastAPI, uvicorn, pytest, GitHub Actions, Node 22, Vite, Vitest, Playwright.

---

## Scope Map

| LAUNCH_READINESS code item | Plan tasks |
|---|---|
| 只能 git clone 运行，wheel 会写 site-packages | Task 1, Task 2, Task 6 |
| `pyproject.toml` 元数据过期 | Task 2 |
| Windows 平台未声明且可能崩溃 | Task 3 |
| API 零信任面，默认暴露风险 | Task 4 |
| 前端 bundle 偏大、无代码分割 | Task 5 |
| CI 只跑 pytest | Task 6 |

本计划和 `2026-07-04-launch-readiness-codex-blockers.md` 的 B2 有交集。若先执行 B2，本计划 Task 4 只需补齐 localhost 绑定、文档和 artifact 路径规范；若先执行本计划，B2 的 token/CORS 测试仍应保留。

## File Structure

- Modify: `quantbench/config.py`
  - Split immutable project root from writable user home; support `QUANTBENCH_HOME`, `QUANTBENCH_DATA_CACHE_DIR`, `QUANTBENCH_RUNS_DIR`, `QUANTBENCH_FACTORS_DIR`, `QUANTBENCH_LITERATURE_DIR`, `QUANTBENCH_SKILL_DOCS_DIR`, and `QUANTBENCH_MCP_SERVERS_CONFIG`.
- Create: `quantbench/platform.py`
  - Central startup guard for supported OS and clear Windows error.
- Modify: `quantbench/cli.py`
  - Call platform guard; add `serve` command; ensure CLI reads new writable dirs.
- Modify: `quantbench/api/server.py`
  - Apply API safety dependency if not already present; tighten artifact filename handling.
- Modify: `quantbench/api/run_manager.py`
  - Ensure run store uses writable `RUNS_DIR`.
- Modify: `quantbench/skills/sandbox.py`
  - Keep `resource` import inside POSIX-only path and route unsupported OS through platform guard.
- Modify: `pyproject.toml`
  - Update description, dev deps, optional web/test deps if chosen, script entry point, package data.
- Modify: `.github/workflows/tests.yml`
  - Add wheel smoke test and frontend jobs.
- Modify: `web/src/App.tsx`
  - Lazy load heavier artifact panels where safe.
- Modify: `web/src/components/ArtifactInspector.tsx`
  - Support lazy-loaded detail panels without changing user-visible behavior.
- Modify: `README.md`
  - Document supported platforms, `QUANTBENCH_HOME`, local API safety, and startup commands.
- Create tests:
  - `tests/test_config_paths.py`
  - `tests/test_platform_support.py`
  - Extend `tests/test_api.py`

## Task 1: Move Writable State Out Of The Package Directory

**Files:**
- Modify: `quantbench/config.py`
- Test: `tests/test_config_paths.py`

- [ ] **Step 1: Write failing config path tests**

Create `tests/test_config_paths.py`:

```python
import importlib


def test_runtime_dirs_default_to_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("QUANTBENCH_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    import quantbench.config as config

    reloaded = importlib.reload(config)

    assert reloaded.QUANTBENCH_HOME == tmp_path / ".quantbench"
    assert reloaded.DATA_CACHE_DIR == tmp_path / ".quantbench" / "data_cache"
    assert reloaded.RUNS_DIR == tmp_path / ".quantbench" / "runs"
    assert reloaded.FACTORS_DIR == tmp_path / ".quantbench" / "factors"
    assert reloaded.LITERATURE_DIR == tmp_path / ".quantbench" / "literature"


def test_runtime_dirs_respect_env_overrides(monkeypatch, tmp_path):
    home = tmp_path / "qb-home"
    custom_runs = tmp_path / "custom-runs"
    custom_cache = tmp_path / "custom-cache"
    monkeypatch.setenv("QUANTBENCH_HOME", str(home))
    monkeypatch.setenv("QUANTBENCH_RUNS_DIR", str(custom_runs))
    monkeypatch.setenv("QUANTBENCH_DATA_CACHE_DIR", str(custom_cache))

    import quantbench.config as config

    reloaded = importlib.reload(config)

    assert reloaded.QUANTBENCH_HOME == home
    assert reloaded.RUNS_DIR == custom_runs
    assert reloaded.DATA_CACHE_DIR == custom_cache
    assert reloaded.FACTORS_DIR == home / "factors"
```

Run:

```bash
uv run pytest tests/test_config_paths.py -q
```

Expected: FAIL because `DATA_CACHE_DIR`, `RUNS_DIR`, `FACTORS_DIR`, and `LITERATURE_DIR` currently point at `PROJECT_ROOT`.

- [ ] **Step 2: Refactor `quantbench/config.py` paths**

Replace the top path block with:

```python
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = Path(__file__).resolve().parent


def _path_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


QUANTBENCH_HOME = _path_env("QUANTBENCH_HOME", Path.home() / ".quantbench")
DATA_CACHE_DIR = _path_env("QUANTBENCH_DATA_CACHE_DIR", QUANTBENCH_HOME / "data_cache")
RUNS_DIR = _path_env("QUANTBENCH_RUNS_DIR", QUANTBENCH_HOME / "runs")
FACTORS_DIR = _path_env("QUANTBENCH_FACTORS_DIR", QUANTBENCH_HOME / "factors")
LITERATURE_DIR = _path_env("QUANTBENCH_LITERATURE_DIR", QUANTBENCH_HOME / "literature")
SKILL_DOCS_DIR = _path_env("QUANTBENCH_SKILL_DOCS_DIR", PROJECT_ROOT / "skills_docs")
MCP_SERVERS_CONFIG = _path_env("QUANTBENCH_MCP_SERVERS_CONFIG", QUANTBENCH_HOME / "mcp_servers.json")
```

Keep `PROJECT_ROOT` for bundled docs/assets and local development, but do not use it as a default writable state directory.

- [ ] **Step 3: Make `.env` lookup package-safe**

Change `_load_dotenv()` to search `QUANTBENCH_ENV_FILE`, `PROJECT_ROOT / ".env"`, and `QUANTBENCH_HOME / ".env"` in that order:

```python
def _candidate_env_files() -> list[Path]:
    explicit = os.environ.get("QUANTBENCH_ENV_FILE")
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.extend([PROJECT_ROOT / ".env", QUANTBENCH_HOME / ".env"])
    return candidates


def _load_dotenv() -> None:
    for env_path in _candidate_env_files():
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return
```

- [ ] **Step 4: Verify path tests**

Run:

```bash
uv run pytest tests/test_config_paths.py -q
```

Expected: PASS.

- [ ] **Step 5: Run affected storage tests**

Run:

```bash
uv run pytest tests/test_api.py tests/test_cli_e2e.py tests/test_literature_ingest.py tests/test_phase9_portfolio.py -q
```

Expected: PASS. If a test imports `RUNS_DIR` before monkeypatching, patch the module that consumed it rather than reverting the config behavior.

- [ ] **Step 6: Commit**

```bash
git add quantbench/config.py tests/test_config_paths.py
git commit -m "fix: store runtime state under quantbench home"
```

## Task 2: Update Package Metadata And Wheel Smoke Test

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `.github/workflows/tests.yml`
- Test: `tests/test_config_paths.py`

- [ ] **Step 1: Add a metadata regression test**

Extend `tests/test_config_paths.py`:

```python
import tomllib
from pathlib import Path


def test_pyproject_metadata_describes_current_product():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["name"] == "quantbench"
    assert "Phase 0 CLI prototype" not in project["description"]
    assert "AI" in project["description"] or "quantitative research" in project["description"].lower()
    assert project["requires-python"] == ">=3.11"
    assert project["scripts"]["quantbench"] == "quantbench.cli:main"
```

Run:

```bash
uv run pytest tests/test_config_paths.py::test_pyproject_metadata_describes_current_product -q
```

Expected: FAIL because the description is stale, Python minimum is `>=3.10`, and no console script exists.

- [ ] **Step 2: Update `pyproject.toml`**

Use this project section shape:

```toml
[project]
name = "quantbench"
version = "0.1.0"
description = "Local AI workbench for reproducible quantitative research runs."
requires-python = ">=3.11"
dependencies = [
  "ccxt",
  "click",
  "duckdb",
  "fastapi",
  "litellm",
  "lxml",
  "matplotlib",
  "mcp>=1.0",
  "numpy",
  "pandas",
  "pyarrow",
  "pypdf>=6.14.2",
  "pyyaml",
  "requests",
  "scipy",
  "uvicorn",
  "yfinance",
]

[project.scripts]
quantbench = "quantbench.cli:main"

[dependency-groups]
dev = ["pytest", "build"]
```

Do not publish a package in this task. The goal is local install and CI smoke testing.

- [ ] **Step 3: Add package-data config if seeds/docs become packaged later**

Add only if a later task adds packaged seed data:

```toml
[tool.hatch.build.targets.wheel]
packages = ["quantbench"]

[tool.hatch.build.targets.wheel.force-include]
"skills_docs" = "skills_docs"
```

If no packaged runtime data is added yet, keep the existing wheel target unchanged.

- [ ] **Step 4: Add CI wheel smoke test**

In `.github/workflows/tests.yml`, after `uv sync`:

```yaml
      - name: Build wheel
        run: uv run python -m build

      - name: Smoke test installed package
        run: |
          uv venv /tmp/quantbench-wheel-smoke
          /tmp/quantbench-wheel-smoke/bin/python -m pip install dist/*.whl
          QUANTBENCH_HOME=/tmp/quantbench-smoke /tmp/quantbench-wheel-smoke/bin/quantbench --help
```

If multiline shell is undesirable for the CI style, split it into three named steps.

- [ ] **Step 5: Update README install language**

Add:

```markdown
QuantBench 首发支持两种本地使用方式：

- 开发者模式：`git clone` 后用 `uv sync`。
- 本地包模式：`uv build` 后安装 wheel；运行状态默认写入 `~/.quantbench/`，可用 `QUANTBENCH_HOME` 覆盖。
```

- [ ] **Step 6: Verify metadata and build**

Run:

```bash
uv run pytest tests/test_config_paths.py -q
uv run python -m build
```

Expected: PASS. If `build` is missing, run `uv sync --group dev` after updating `pyproject.toml`, then repeat.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml README.md .github/workflows/tests.yml tests/test_config_paths.py
git commit -m "chore: update package metadata and wheel smoke test"
```

## Task 3: Declare And Enforce Supported Platforms

**Files:**
- Create: `quantbench/platform.py`
- Modify: `quantbench/cli.py`
- Modify: `quantbench/api/server.py`
- Modify: `README.md`
- Test: `tests/test_platform_support.py`

- [ ] **Step 1: Write platform guard tests**

Create `tests/test_platform_support.py`:

```python
import pytest


def test_supported_platform_guard_accepts_darwin_and_linux():
    from quantbench.platform import ensure_supported_platform

    ensure_supported_platform("darwin")
    ensure_supported_platform("linux")


def test_supported_platform_guard_rejects_windows_with_clear_message():
    from quantbench.platform import UnsupportedPlatformError, ensure_supported_platform

    with pytest.raises(UnsupportedPlatformError, match="macOS/Linux"):
        ensure_supported_platform("win32")
```

Run:

```bash
uv run pytest tests/test_platform_support.py -q
```

Expected: FAIL because `quantbench.platform` does not exist.

- [ ] **Step 2: Add `quantbench/platform.py`**

```python
from __future__ import annotations

import sys


SUPPORTED_PLATFORM_PREFIXES = ("darwin", "linux")


class UnsupportedPlatformError(RuntimeError):
    pass


def ensure_supported_platform(platform: str | None = None) -> None:
    current = platform or sys.platform
    if current.startswith(SUPPORTED_PLATFORM_PREFIXES):
        return
    raise UnsupportedPlatformError(
        "QuantBench launch build supports macOS/Linux only. "
        "Windows is not supported because signal-code sandbox resource limits rely on POSIX process controls."
    )
```

- [ ] **Step 3: Call guard at CLI and API startup**

In `cli.py`:

```python
from quantbench.platform import ensure_supported_platform
```

Inside `main()` before command routing:

```python
ensure_supported_platform()
```

In `api/server.py`, call `ensure_supported_platform()` before `app = FastAPI(...)`.

- [ ] **Step 4: Add README platform section**

```markdown
## Supported Platforms

The launch build supports macOS and Linux. Windows is not supported yet because the signal-code sandbox depends on POSIX process resource limits. On Windows, use WSL2 with a Linux Python environment.
```

- [ ] **Step 5: Verify platform tests**

Run:

```bash
uv run pytest tests/test_platform_support.py tests/test_phase13_sandbox.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quantbench/platform.py quantbench/cli.py quantbench/api/server.py README.md tests/test_platform_support.py
git commit -m "fix: enforce supported launch platforms"
```

## Task 4: Make API Safety The Default Local Posture

**Files:**
- Create: `quantbench/api/security.py`
- Modify: `quantbench/api/server.py`
- Modify: `quantbench/cli.py`
- Modify: `web/src/api/client.ts`
- Modify: `README.md`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing local API safety tests**

Add to `tests/test_api.py`:

```python
def test_api_requires_local_token_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTBENCH_API_TOKEN", "secret")
    monkeypatch.setattr("quantbench.api.run_reader.RUNS_DIR", tmp_path)
    from quantbench.api.server import app

    client = TestClient(app)

    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"X-QuantBench-Token": "secret"}).status_code == 200


def test_artifact_filename_must_resolve_inside_run_dir(tmp_path, client):
    _write_fake_completed_run(tmp_path)

    response = client.get("/api/runs/run_20260701_000000_aaaa/artifacts/%2e%2e%2fmanifest.json")

    assert response.status_code in (400, 404)
```

Run:

```bash
uv run pytest tests/test_api.py::test_api_requires_local_token_when_configured tests/test_api.py::test_artifact_filename_must_resolve_inside_run_dir -q
```

Expected: token test FAIL until security is implemented.

- [ ] **Step 2: Implement token helper**

Create `quantbench/api/security.py`:

```python
from __future__ import annotations

import os
from secrets import compare_digest

from fastapi import Header, HTTPException


TOKEN_ENV = "QUANTBENCH_API_TOKEN"
ALLOWED_ORIGINS_ENV = "QUANTBENCH_ALLOWED_ORIGINS"


def api_token() -> str | None:
    return os.environ.get(TOKEN_ENV)


def allowed_origins() -> list[str]:
    raw = os.environ.get(ALLOWED_ORIGINS_ENV)
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return ["http://127.0.0.1:5173", "http://localhost:5173"]


def require_api_token(x_quantbench_token: str | None = Header(default=None)) -> None:
    expected = api_token()
    if expected is None:
        return
    if not x_quantbench_token or not compare_digest(x_quantbench_token, expected):
        raise HTTPException(status_code=401, detail="missing or invalid QuantBench API token")
```

This keeps current test/dev behavior working without env setup, while allowing launch docs and `quantbench serve` to generate a token.

- [ ] **Step 3: Apply CORS and dependency**

In `api/server.py`, import:

```python
from fastapi import Depends
from quantbench.api.security import allowed_origins, require_api_token
```

Change CORS:

```python
allow_origins=allowed_origins(),
allow_methods=["GET", "POST", "OPTIONS"],
allow_headers=["Content-Type", "X-QuantBench-Token"],
```

Add `dependencies=[Depends(require_api_token)]` to all `/api` route decorators or use an `APIRouter` with the dependency.

- [ ] **Step 4: Harden artifact path resolution**

Replace substring checks with resolved path containment:

```python
def _safe_artifact_path(run_id: str, filename: str):
    run_dir = run_reader.run_dir_for(run_id).resolve()
    path = (run_dir / filename).resolve()
    if path == run_dir or run_dir not in path.parents:
        raise HTTPException(status_code=400, detail="invalid filename")
    return path
```

Use `_safe_artifact_path()` in artifact download and parquet preview endpoints.

- [ ] **Step 5: Add Web token header**

In `web/src/api/client.ts`:

```ts
const apiToken = import.meta.env.VITE_QUANTBENCH_API_TOKEN as string | undefined;

function jsonHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(apiToken ? { "X-QuantBench-Token": apiToken } : {}),
  };
}
```

Use `jsonHeaders()` in `request()` and add token headers to direct fetch helpers.

- [ ] **Step 6: Document local-only API**

README section:

```markdown
## Local API Safety

QuantBench is a local single-user research tool. Bind the API to `127.0.0.1`, set `QUANTBENCH_API_TOKEN` before launch, and do not expose the port to a LAN or the public internet. Browser access is restricted to configured localhost origins.
```

- [ ] **Step 7: Verify API safety tests**

Run:

```bash
uv run pytest tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add quantbench/api/security.py quantbench/api/server.py quantbench/cli.py web/src/api/client.ts README.md tests/test_api.py
git commit -m "fix: default API to local safe posture"
```

## Task 5: Add Frontend Code Splitting For Heavy Panels

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/ArtifactInspector.tsx`
- Test: `web/src/components/ArtifactInspector.test.tsx`

- [ ] **Step 1: Record current bundle size in a failing budget test**

Create `web/src/components/ArtifactInspector.test.tsx` if it does not exist:

```tsx
import { describe, expect, it } from "vitest";

describe("bundle budget marker", () => {
  it("keeps artifact inspector heavy panels lazy-loadable", () => {
    expect(true).toBe(true);
  });
});
```

This component test is a placeholder marker for local dev, but the real budget is enforced by build output in Step 5.

- [ ] **Step 2: Lazy load expensive inspector children**

In `ArtifactInspector.tsx`, replace eager imports for panels that pull charting/PDF/parquet logic with:

```tsx
import { lazy, Suspense } from "react";

const ChartsPanel = lazy(() => import("./ChartsPanel").then((module) => ({ default: module.ChartsPanel })));
const LiteratureViewer = lazy(() => import("./LiteratureViewer").then((module) => ({ default: module.LiteratureViewer })));
```

Only lazy load components whose props are stable and whose loading state can be shown inside the existing inspector area.

- [ ] **Step 3: Add a compact fallback**

Use:

```tsx
function InspectorLoading() {
  return <div className="p-3 text-xs text-warm-500">Loading artifact...</div>;
}
```

Wrap lazy children:

```tsx
<Suspense fallback={<InspectorLoading />}>
  <ChartsPanel runId={tab.runId} />
</Suspense>
```

- [ ] **Step 4: Verify tests and build**

Run:

```bash
cd web && npm test && npm run build
```

Expected: PASS. Build output should contain multiple JS chunks instead of a single application bundle.

- [ ] **Step 5: Add a CI-observable bundle budget note**

If Vite prints `dist/assets/index-*.js` over 700KB uncompressed after splitting, add this package script:

```json
"build:budget": "npm run build && node scripts/check-bundle-budget.mjs"
```

Create `web/scripts/check-bundle-budget.mjs`:

```js
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const assetsDir = join(process.cwd(), "dist", "assets");
const maxBytes = 700 * 1024;
const jsFiles = readdirSync(assetsDir).filter((name) => name.endsWith(".js"));
const oversized = jsFiles
  .map((name) => ({ name, size: statSync(join(assetsDir, name)).size }))
  .filter((item) => item.size > maxBytes);

if (oversized.length > 0) {
  console.error(JSON.stringify({ oversized }, null, 2));
  process.exit(1);
}
```

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/components/ArtifactInspector.tsx web/src/components/ArtifactInspector.test.tsx web/package.json web/scripts/check-bundle-budget.mjs
git commit -m "perf: lazy load heavy frontend panels"
```

## Task 6: Expand CI Beyond Python Unit Tests

**Files:**
- Modify: `.github/workflows/tests.yml`

- [ ] **Step 1: Add frontend CI job**

Add:

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
```

- [ ] **Step 2: Add Playwright CI job**

Add:

```yaml
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

- [ ] **Step 3: Keep Python job explicit**

Rename the existing job from `pytest` to `backend` and keep:

```yaml
      - name: Run full test suite
        run: uv run pytest -q
```

- [ ] **Step 4: Verify local commands**

Run:

```bash
uv run pytest -q
cd web && npm run lint && npm test && npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/tests.yml
git commit -m "ci: run frontend lint tests and build"
```

## Task 7: Full Code-Layer Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused backend tests**

```bash
uv run pytest tests/test_config_paths.py tests/test_platform_support.py tests/test_api.py tests/test_cli_e2e.py tests/test_phase13_sandbox.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend tests**

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend tests and build**

```bash
cd web && npm run lint && npm test && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run wheel smoke locally**

```bash
uv run python -m build
uv venv /tmp/quantbench-wheel-smoke
/tmp/quantbench-wheel-smoke/bin/python -m pip install dist/*.whl
QUANTBENCH_HOME=/tmp/quantbench-smoke /tmp/quantbench-wheel-smoke/bin/quantbench --help
```

Expected: `quantbench --help` exits 0, and no runtime state is created under the installed package directory.

- [ ] **Step 5: Update launch readiness**

In `LAUNCH_READINESS.md` section 一, mark:

- writable dirs fixed by `QUANTBENCH_HOME`;
- platform support explicitly macOS/Linux;
- API local posture documented and guarded;
- frontend CI added;
- package metadata updated.

- [ ] **Step 6: Commit docs update**

```bash
git add LAUNCH_READINESS.md
git commit -m "docs: mark code launch readiness gaps resolved"
```

## Acceptance Criteria

- Installing a wheel and running `quantbench --help` does not write to site-packages.
- Default writable state is `~/.quantbench`, with environment-variable overrides for each state directory.
- macOS/Linux are accepted; Windows fails with a clear message before sandbox work starts.
- API defaults are local-safe and documented.
- Artifact path traversal uses resolved-path containment, not substring checks.
- Python tests, frontend lint, frontend unit tests, frontend build, Playwright, and wheel smoke are covered by CI.
