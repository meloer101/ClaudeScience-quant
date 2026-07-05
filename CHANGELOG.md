# Changelog

## 0.2.0 - 2026-07-05

### MCP & Skills customization

- Added Claude Code-compatible `mcpServers` JSON config format with user (`~/.quantbench/mcp.json`) and project (`.mcp.json`) scopes, project overriding user.
- Added `~/.quantbench/settings.json` / `.quantbench/settings.json` for per-server and per-skill enable/disable state, applied on every run (no restart required).
- Added REST endpoints under `/api/config` for listing, upserting, importing, deleting, enabling/disabling, and connection-testing MCP servers, and listing/enabling/disabling/importing/deleting Skills.
- Added a Sidebar **Customize** panel in the Web workspace (Skills and MCP tabs) to paste `mcpServers` JSON, add servers, toggle enablement, and test connections without touching files.
- Added `quantbench mcp add/add-json/import/list/get/remove/enable/disable/migrate` and `quantbench skill enable/disable` CLI subcommands, aligned with `claude mcp` naming; `migrate` converts the legacy `mcp_servers.json` format.
- Extended MCP transport support to `sse` and `streamable-http` in addition to `stdio`.
- Shipped three key-free example MCP servers in the repo's project-scope `.mcp.json` (`fetch`, `sequential-thinking`, `time`), disabled by default so they add no first-run cost; enable any from the Customize panel or `quantbench mcp enable <name>`.
- Disable lists (`disabledServers` / `disabledSkills`) now union across user and project scopes, and enabling a server/skill clears it from every scope — so a user can turn on a project-shipped default-disabled server from the Customize panel (user scope) and have it take effect.
- Remote MCP connection tests now report a distinct `needs-authorization` state (surfaced in the Customize panel and `quantbench mcp test`) when a server answers with an auth challenge, instead of a generic failure. Automatic OAuth authorization-code flow is not yet implemented.

### Onboarding

- `quantbench serve` now preflights `uv`/`node`/`npm` and prints an actionable install hint when one is missing, and automatically runs `npm install` on first run when `web/node_modules` is absent — so a fresh clone starts with a single command instead of failing on a missing web build.
- `quantbench examples seed` now restores four real, pre-generated example research sessions (equity cross-sectional momentum, beta/sector-neutralized low-volatility, single-asset RSI mean-reversion, single-asset moving-average trend) instead of one placeholder run. Each is a genuine run with its full artifacts and Reviewer/Critic reports, so a first-time user opens the workspace to a ready set of conversations to explore. Seeding is idempotent.

## 0.1.0 - 2026-07-04

### First trusted-user release fixes

- Changed default execution fill from `close_t` to `open_t+1`.
- Explicit `close_t` runs now receive a Reviewer warning because same-close fills are optimistic.
- Fixed crypto perpetual funding cost estimation: funding history is paginated and intraday funding rows are aggregated into rebalance holding periods.
- Added local API token enforcement, localhost CORS allowlist defaults, and upload-based literature import to close the local-file ingest exposure.
- Conditioned crypto funding warnings on aligned coverage and failed-symbol metadata instead of warning unconditionally.

## 0.1.0-alpha - 2026-07-04

### Initial implementation

- Local AI workbench for reproducible quant research runs.
- Deterministic Reviewer with statistical, execution, data-quality, and cost findings.
- FastAPI + React local workspace for run browsing, artifacts, library, comparison, and paper workflows.
- Launch limitations: macOS/Linux first, research artifacts are not investment advice, and provider coverage limits remain documented in run warnings.
