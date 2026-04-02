---
name: campaign-status
description: Check if Google/Meta/Microsoft Ads campaigns are on, off, or paused via ad platform APIs
version: 1.0.0
author: marketing-autopilot
license: MIT
metadata:
  hermes:
    tags: [Paid Search, Google Ads, Campaign Management, Agency]
    requires_tools: [bash]
required_environment_variables:
  - name: GOOGLE_ADS_DEVELOPER_TOKEN
    prompt: "Enter your Google Ads API developer token"
    help: "Get one at https://developers.google.com/google-ads/api/docs/get-started/dev-token"
    required_for: "Google Ads API access"
  - name: GOOGLE_ADS_JSON_KEY_PATH
    prompt: "Path to your Google Ads service account JSON key file"
    help: "Create at https://console.cloud.google.com → IAM → Service Accounts"
    required_for: "Google Ads API authentication"
  - name: GOOGLE_ADS_LOGIN_CUSTOMER_ID
    prompt: "Your MCC (manager) account ID (no dashes)"
    help: "The top-level manager account that has access to all client accounts"
    required_for: "Multi-client account access"
---

# Campaign Status Checker

Check whether any campaign across any client account is enabled, paused, or removed — and answer status questions from Slack instantly.

## When to Use

Activate when someone asks anything like:
- "Is the [client] [campaign] turned on?"
- "Did we pause [campaign name]?"
- "What's the status of [client]'s campaigns?"
- "Is [campaign] running / live / active / on / off?"
- "Which campaigns are enabled for [client]?"
- "Has the [promo/sale] campaign been activated?"

## Quick Reference

| Command | What it does |
|---------|-------------|
| `bash scripts/check_campaign.py --client "Nike" --campaign "Q2 Awareness"` | Check a specific campaign |
| `bash scripts/check_campaign.py --client "Nike" --list-all` | List all campaigns + statuses for a client |
| `bash scripts/check_campaign.py --search "black friday"` | Search campaigns by name across all clients |

## Procedure

1. **Parse the question** to extract:
   - **Client name** (e.g., "Nike", "Acme Corp") — match against `config/client-accounts.json`
   - **Campaign name or keyword** (e.g., "Q2 Awareness", "Black Friday", "brand")
   - **What they want to know** (status? budget? start date?)

2. **Check access control** — verify the Slack user asking is authorized to view this client's data. Check `config/access-control.json`. If not authorized, respond: "I don't have permission to check that account for you. Reach out to [account lead]."

3. **Run the lookup script**:
   ```bash
   python3 scripts/check_campaign.py --client "<client_name>" --campaign "<campaign_name>"
   ```

4. **Read the script output** (JSON format):
   ```json
   {
     "client": "Nike",
     "campaign": "Q2 Awareness",
     "status": "ENABLED",
     "budget_micros": 50000000,
     "budget_daily": "$50.00",
     "start_date": "2026-03-15",
     "end_date": "2026-06-30",
     "network": "SEARCH",
     "checked_at": "2026-04-02T14:30:00Z"
   }
   ```

5. **Format a natural response**. Examples:
   - "Yes, Nike's Q2 Awareness campaign is **live** (ENABLED). Running at $50/day on Search, started March 15."
   - "No, the Black Friday campaign is currently **paused**. It was paused on Nov 27."
   - "I found 3 campaigns matching 'brand' for Acme Corp: [list with statuses]"

6. **Log the query** — append to `~/.hermes/state/campaign-query-log.jsonl`:
   ```json
   {"ts": "...", "asked_by": "slack:@alice", "client": "Nike", "campaign": "Q2 Awareness", "result": "ENABLED", "channel": "#paid-search"}
   ```

## Pitfalls

- **Fuzzy campaign names**: People rarely use exact campaign names. Use fuzzy matching — "nike q2" should match "Nike | Q2 Awareness | Search | US". The script handles this.
- **Multiple matches**: If the search matches multiple campaigns, list all of them with statuses rather than guessing which one they meant.
- **Stale data**: The API returns real-time status. Always include the timestamp in your response.
- **Access denied**: If the service account doesn't have access to a client account, the script returns an error. Tell the user to contact their account lead.

## Verification

After responding, the user should be able to verify the status matches what they see in Google Ads UI. The script pulls live data so there should be no discrepancy.

## Privacy Notes

- All API calls happen locally — campaign data never passes through any third-party servers
- The LLM only sees the structured result (status, budget, dates), not raw account data
- Every query is audit-logged with who asked, what they asked, and what was returned
- Access control restricts who can query which client accounts
