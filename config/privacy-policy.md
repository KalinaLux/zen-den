# Privacy & Data Handling Policy

## How This System Handles Client Data

### Architecture Overview

```
Slack question → Hermes (local) → LLM parses intent → Local script calls Google Ads API → Response
```

### What the LLM (OpenAI) Sees

- The user's question (e.g., "Is Nike Q2 campaign on?")
- Structured results from the API (e.g., "status: ENABLED, budget: $50/day")
- The skill instructions (SKILL.md files)

### What the LLM Does NOT See

- Full account data dumps
- Other clients' data not relevant to the question
- Billing or payment information
- Historical performance data (unless specifically asked)
- Login credentials or API keys

### Privacy Layers

1. **Read-only API access**: The Google Ads service account can only READ campaign data. It cannot modify, pause, enable, or delete anything.

2. **Access control**: `config/access-control.json` restricts which Slack users can query which client accounts. This prevents cross-client data leakage within the team.

3. **Data minimization**: Scripts fetch only the specific fields needed to answer the question (status, budget, dates), not everything in the account.

4. **Local execution**: All Google Ads API calls happen on the machine running Hermes. Campaign data flows directly from Google to this machine — it does not pass through OpenAI or any third party.

5. **Audit logging**: Every query is logged to `~/.hermes/state/` with:
   - Who asked (Slack username)
   - What client/campaign was queried
   - What data was returned
   - Timestamp and channel

### The OpenAI Tradeoff

The question text and structured response are sent to OpenAI's API for the LLM to formulate a natural-language response. Per OpenAI's API data usage policy (as of March 2026):

- API inputs and outputs are NOT used to train models
- Data is retained for up to 30 days for abuse monitoring, then deleted
- Enterprise/Team plans offer zero-retention options

### Options for Stricter Privacy

If Hawke Media's security team requires stricter data handling:

1. **Local model**: Switch Hermes to use a local LLM via Ollama (e.g., Llama 3.3, Hermes 3). Zero data leaves the machine. Tradeoff: slower, less capable responses.

2. **OpenAI Enterprise**: Zero-retention API with contractual guarantees.

3. **Hybrid approach**: Use local model for campaign-data queries (sensitive), OpenAI for general Slack triage (not sensitive).

4. **Redact before sending**: Modify scripts to anonymize client names before they reach the LLM (e.g., "Client A" instead of "Nike"). The mapping stays local.

### Compliance Notes

- No campaign data is stored in any third-party cloud service
- All state files are in `~/.hermes/state/` on the local machine
- Audit logs can be exported for compliance review
- The system can be configured to auto-purge logs after N days
