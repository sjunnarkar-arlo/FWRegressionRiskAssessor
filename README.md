# FW Regression Risk Assessor

A single-page internal tool for Arlo firmware QA. Drop a release notes email, get a ranked list of Jira tickets, subsystem risk scores, and Zephyr test cycles to execute — all cross-referenced against the actual changes in the release.

---

## How it works

```
Email attachment (.msg / .eml)
        │
        ▼
  Extract ticket keys  ──►  Jira: fetch full ticket details
        │
        ▼
  Confluence: model docs + firmware notes
        │
        ▼
  Zephyr: template folder → cycle list → test cases per cycle
        │
        ▼
  Claude (Bedrock) or rule-based scoring
        │
        ▼
  Risk report: subsystems + test cycles to execute
```

---

## Running locally

Requires VPN for MCP (Arlochat) features.

```bash
node proxy.js
```

Then open: [http://localhost:8082/firmware-regression-assessor.html](http://localhost:8082/firmware-regression-assessor.html)

The proxy serves the HTML file and forwards `/mcp/*` requests to the Arlochat internal ALB.

---

## Usage

### 1. Attach a release notes email

Drag and drop (or click to browse) a `.msg` or `.eml` file from Outlook.

- **Model ID** and **FW Version** are extracted automatically from the email subject line.  
  Subject format: `Lory Release Notes - AVD6001-0.100.159_b075390 - Release to QA`
- Alternatively, paste the email body directly into the fallback text area.

### 2. Choose a data source

| Option | What it does |
|---|---|
| **GitHub commits** | Searches arlo-engineering GitHub repos for commits matching the FW version tag/branch, extracts Jira ticket keys from commit messages |
| **Email release notes** | Parses ticket keys directly from the attached release notes email |

### 3. Enable Direct Arlochat MCP

Check the **Direct Arlochat MCP** box (requires VPN). This connects to the Arlochat MCP server over SSE and gives the tool access to GitHub, Jira, Confluence, and Zephyr.

### 4. (Optional) Add AWS Bedrock credentials

For AI-powered risk analysis instead of rule-based scoring:

| Field | Notes |
|---|---|
| Access Key ID | IAM user key — scope to `bedrock:InvokeModel` only |
| Secret Access Key | Never shared or stored |
| Session Token | Recommended — use STS short-lived credentials |
| Region | Default: `us-east-1` |
| Model ID | Default: `us.anthropic.claude-sonnet-4-5-20251001-v1:0` |

Leave credentials blank to run rule-based scoring with no external AI call.

**Security:** Use STS temporary credentials (`aws sts get-session-token`) with a short TTL. The IAM policy should allow only `bedrock:InvokeModel` on the specific model ARN. Long-lived IAM keys are not recommended.

### 5. Click Run Assessment

The tool runs through up to 5 steps:

1. Connect to Arlochat MCP
2. Fetch commits (GitHub) or parse tickets (email)
3. Jira: load full ticket details for all extracted keys
4. Confluence + Zephyr: pull model docs and template test cycles
5. Claude (Bedrock) or rule-based: score risk, rank subsystems, recommend test cycles

---

## Output

- **Risk score** (0–100) with HIGH / MEDIUM / LOW overall rating
- **Subsystems** — each flagged area with risk level, reason, and linked tickets
- **Test cycles to execute** — pulled from the Zephyr template folder for the device's project, cross-referenced against the actual changes. P1 = directly impacted, P2 = shared dependency risk, P3 = broad regression net.
- **Key QA advice** — specific guidance for the release

---

## Demo mode

Run without MCP enabled and without Bedrock credentials to load a pre-baked demo assessment. Useful for UI development or offline review.

---

## Project structure

| File | Purpose |
|---|---|
| `firmware-regression-assessor.html` | Single-file app — all UI, logic, and MCP client |
| `proxy.js` | Local dev proxy: serves HTML + forwards `/mcp/*` to Arlochat ALB |
| `proxy.py` | Older Python proxy (superseded by `proxy.js`, kept for reference) |

---

## Arlochat MCP

- **ALB:** `internal-arlochat-mcp-alb-880426873.us-east-1.elb.amazonaws.com:8080`
- **Transport:** SSE (`GET /sse`) + JSON-RPC 2.0 (`POST /messages/?session_id=…`)
- **Auth:** none — VPN access only
- **Tools used:** `github_cli`, `jira_read_issue`, `jira_search`, `confluence_search`, `confluence_read_page`, `zephyr_list`, `zephyr_get_executions`, `zephyr_get_test_case`

---

## Supported email formats

| Format | Notes |
|---|---|
| `.msg` | Outlook OLE2 binary — HTML body extracted directly from the binary, no external parser needed |
| `.eml` | RFC 2822 MIME — full multipart parser handles quoted-printable and base64 encoding |
| `.txt` / paste | Plain text fallback |

Model ID and FW version are parsed from the email subject line on attach. If the subject pattern isn't found in the binary, the filename is used as a fallback.
