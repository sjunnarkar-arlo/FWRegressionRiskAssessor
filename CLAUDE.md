# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

Run without MCP enabled and without Bedrock credentials to load the pre-baked demo assessment (useful for UI development offline).

## Architecture

The app is a **single HTML file** (`firmware-regression-assessor.html`) with all CSS, UI, and JS inlined. There is no build step, bundler, or package.json — edits to the HTML are live on the next browser refresh.

`proxy.js` is a thin Node.js HTTP server that:
- Serves `firmware-regression-assessor.html` as a static file
- Rewrites SSE `endpoint` events so the browser can reach the Arlochat MCP ALB through `localhost:8082/mcp/*` (avoids CORS and internal-DNS issues)

### Key JS functions in the HTML (by concern)

| Function | Purpose |
|---|---|
| `runAssessment()` | Main orchestrator — wires together all steps, reads sidebar inputs |
| `McpClient` class | SSE + JSON-RPC 2.0 MCP transport; `connect()` → `call(tool, args)` |
| `discoverCommits()` / `discoverCommitsViaMcp()` | GitHub commit search via Bedrock tool-use or MCP `github_cli` |
| `fetchJiraDetails()` / `fetchJiraDetailsViaMcp()` | Bulk-fetch Jira tickets via Bedrock or MCP |
| `fetchConfluenceContextViaMcp()` | Pull model-specific Confluence docs |
| `fetchZephyrTestCyclesViaMcp()` | Walk Zephyr template folder → cycle list → test cases |
| `claudeAssess()` | Build prompt + call Claude via Bedrock (SigV4 signed) → structured JSON |
| `ruleBasedAssess()` | Offline fallback scoring when no Bedrock credentials are provided |
| `renderResults()` | Render the risk report, subsystem cards, and test cycles into the DOM |
| `parseEmlToText()` | Full RFC 2822 MIME parser (handles quoted-printable, base64, multipart) |
| `mcpCall()` | Low-level Bedrock `converse` API call with tool definitions |
| `sigV4Headers()` | Pure-JS AWS SigV4 request signing (no SDK) using WebCrypto |

### Data flow

```
Email (.msg/.eml) or GitHub commits
        │
        ▼
  extractTicketKeys()  →  Jira ticket details
        │
        ▼
  Confluence model docs + Zephyr test cycles
        │
        ▼
  claudeAssess() (Bedrock) OR ruleBasedAssess()
        │
        ▼
  renderResults() → DOM
```

### Two AI paths

1. **Bedrock path** — `claudeAssess()` signs requests with `sigV4Headers()` and calls `bedrock-runtime` directly from the browser via the proxy. The prompt includes all ticket/Confluence/Zephyr context in a single `converse` call; response is parsed JSON.
2. **Rule-based path** — `ruleBasedAssess()` applies keyword/component heuristics locally with no network calls. Triggered when Bedrock credentials are absent.

## Arlochat MCP

- ALB: `http://internal-arlochat-mcp-alb-880426873.us-east-1.elb.amazonaws.com:8080`
- Transport: SSE (GET `/sse`) + JSON-RPC 2.0 (POST `/messages/?session_id=...`)
- No auth token required — VPN access only
- Tools used: `github_cli`, `jira_read_issue`, `jira_search`, `confluence_search`, `confluence_read_page`, `zephyr_list`, `zephyr_get_executions`, `zephyr_get_test_case`

## AWS Bedrock credentials

Use STS temporary credentials (`aws sts get-session-token --profile bedrock`) with a short TTL. The IAM policy should scope to `bedrock:InvokeModel` on the specific model ARN only. Default model: `us.anthropic.claude-sonnet-4-5-20251001-v1:0` in `us-east-1`.
