# Regression Risk Assessor

A single-page internal tool for Arlo QA. Provide a firmware release notes email or a software release version, get a ranked list of Jira tickets, subsystem risk scores, and Zephyr test cycles to execute — all cross-referenced against the actual changes in the release.

---

## How it works

### Firmware (FW) flow

```
Email attachment (.msg / .eml)
        │
        ▼
  Extract ticket keys  ──►  Jira: fetch full ticket details
        │
        ▼
  Claude (Bedrock): queries FWQE Zephyr test cases, Confluence model docs
        │                   (or rule-based scoring if no Bedrock credentials)
        ▼
  Risk report: subsystems + test cycles to execute + coverage gaps
```

### Software (SW) flow

```
Release version (iOS / Android / Web)
        │
        ▼
  GitHub: search arlo-engineering repos for commits matching version
        │
        ▼
  Jira: fetch full ticket details for extracted keys
        │
        ▼
  Claude (Bedrock) or rule-based: score risk, recommend test cycles
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

### 1. Select release type

Choose **Firmware (FW)** or **Software (SW)** from the Release type dropdown. The sidebar adjusts to show only the relevant fields.

---

### Firmware (FW) mode

#### Release info
- **Model ID** and **FW Version** are extracted automatically from the email subject on file attach.  
  Subject format: `Lory Release Notes - AVD6001-0.100.159_b075390 - Release to QA`

#### Commit source
With Direct Arlochat MCP enabled, choose:

| Option | What it does |
|---|---|
| **Email release notes** | Parses ticket keys directly from the attached release notes file (default for FW) |
| **GitHub commits** | Searches arlo-engineering repos for commits matching the FW version tag/branch |

#### Attach release notes
Drag and drop (or click to browse) a `.msg` or `.eml` file. Alternatively, paste the email body into the fallback text area.

---

### Software (SW) mode

#### Client type
Select the client being released — **iOS**, **Android**, or **Web**. Only the version field for the selected client is shown.

| Client | Version field | GitHub repo searched |
|---|---|---|
| iOS | iOS Version (e.g. `4.29.1.0`) | `ios` |
| Android | Android Version (e.g. `4.29.1.0`) | `android-ori` |
| Web | Web Version (e.g. `1.5.2`) | `webclient` |

SW mode always uses GitHub commits as the data source — no email attachment needed.

---

### 2. Enable Direct Arlochat MCP

Check the **Direct Arlochat MCP** box (requires VPN). This connects to the Arlochat MCP server over SSE and gives the tool access to GitHub, Jira, Confluence, and Zephyr.

### 3. (Optional) Add AWS Bedrock credentials

For AI-powered analysis instead of rule-based scoring. When credentials are provided, Claude drives its own Zephyr and Confluence queries via tool use — it reads test case titles directly from the FWQE Zephyr project and cross-references them against the release changes to produce accurate cycle names.

| Field | Notes |
|---|---|
| Access Key ID | IAM key — scope to `bedrock:InvokeModel` only |
| Secret Access Key | Never shared or stored |
| Region | Default: `us-east-1` |
| Model ID | Default: `global.anthropic.claude-opus-4-6-v1` |

Leave credentials blank to run rule-based scoring with no external AI call.

**Security:** Use an IAM key scoped to `bedrock:InvokeModel` only. Never use root or broad IAM keys.

### 4. Click Run Assessment

The tool runs through up to 5 steps:

1. Connect to Arlochat MCP
2. Fetch commits (GitHub) or parse tickets (email release notes)
3. Jira: load full ticket details for all extracted keys
4. Bedrock: query FWQE Zephyr test cases + Confluence docs (or pre-fetch for rule-based)
5. Score risk, rank subsystems, recommend test cycles

---

## Output

- **Risk score** (0–100) with HIGH / MEDIUM / LOW overall rating
- **Subsystems at risk** — each flagged area with risk level, reason, and linked tickets
- **Test cycles to execute** — cross-referenced against FWQE Zephyr test case titles. P1 = directly impacted area, P2 = shared dependency risk, P3 = broad regression safety net. Each cycle includes the reason it was included and the tickets driving it.
- **Coverage gaps** *(Bedrock mode only)* — functional areas touched by tickets that have no matching Zephyr test case, with recommendations for what additional coverage to add
- **Key QA advice** — specific guidance for the release

---

## Demo mode

Run without MCP enabled to load a pre-baked demo assessment (FW release). Useful for UI review or offline testing without VPN.

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
- **Tools used:** `github_cli`, `jira_read_issue`, `jira_search`, `confluence_search`, `confluence_read_page`, `zephyr_list`, `zephyr_get_executions`

---

## Supported email formats (FW mode)

| Format | Notes |
|---|---|
| `.msg` | Outlook OLE2 binary — HTML body extracted directly, no external parser needed |
| `.eml` | RFC 2822 MIME — full multipart parser handles quoted-printable and base64 encoding |
| `.txt` / paste | Plain text fallback |

Model ID and FW version are parsed from the email subject line on attach. If the subject pattern isn't found, the filename is used as a fallback.
