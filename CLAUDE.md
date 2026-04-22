# FW Regression Risk Assessor — Claude Code guidelines

## Git workflow

- **Never commit directly to `master`.**
- Start every task on a feature branch: `git checkout -b feature/<short-description>`
- Commit work there, then open a PR into `master` via `gh pr create`.
- Branch names: `feature/`, `fix/`, or `chore/` prefix + kebab-case description.
  Examples: `feature/add-model-filter`, `fix/mcp-timeout`, `chore/update-deps`

## Running locally

Start the proxy (requires VPN for MCP features):
```
node proxy.js
```
Open: http://localhost:8082/firmware-regression-assessor.html

## Project structure

| File | Purpose |
|---|---|
| `firmware-regression-assessor.html` | Single-file app — all UI, logic, and MCP client |
| `proxy.js` | Local dev proxy: serves HTML + forwards `/mcp/*` to Arlochat ALB |
| `proxy.py` | Older Python proxy (superseded by proxy.js, kept for reference) |

## Arlochat MCP

- ALB: `http://internal-arlochat-mcp-alb-880426873.us-east-1.elb.amazonaws.com:8080`
- Transport: SSE (GET `/sse`) + JSON-RPC 2.0 (POST `/messages/?session_id=...`)
- No auth token required — VPN access only
- Tools used: `github_cli`, `jira_read_issue`, `jira_search`, `confluence_search`, `confluence_read_page`, `zephyr_list`
