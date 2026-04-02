# Quick Start — 10 Minutes to "Is the Campaign On?" Automation

## Step 1: Install Skills (1 minute)

```bash
cd marketing-autopilot
chmod +x install.sh
./install.sh
```

## Step 2: Set Up OpenAI (1 minute)

```bash
hermes config set llm.provider openai
hermes config set llm.api_key sk-YOUR-OPENAI-KEY
hermes config set llm.model gpt-4o
```

## Step 3: Set Up Google Ads API Access (5 minutes)

This is the part that lets the AI actually check if campaigns are on/off.

### 3a. Google Cloud Setup
1. Go to https://console.cloud.google.com
2. Create a project (or use existing)
3. Enable the "Google Ads API"
4. Go to IAM → Service Accounts → Create Service Account
5. Download the JSON key file → save somewhere safe (e.g., `~/.config/google-ads-key.json`)

### 3b. Google Ads MCC Access
1. In Google Ads, go to Admin → Access and security
2. Add the service account email (from the JSON key) with **Read-only** access
3. Note your MCC account ID (the number at the top of Google Ads, no dashes)

### 3c. Developer Token
1. Go to https://ads.google.com/aw/apicenter
2. Apply for API access (if you haven't already — Hawke Media likely already has one)

### 3d. Set Environment Variables
Add to your `~/.zshrc` or `~/.bashrc`:
```bash
export GOOGLE_ADS_DEVELOPER_TOKEN='your-dev-token'
export GOOGLE_ADS_JSON_KEY_PATH="$HOME/.config/google-ads-key.json"
export GOOGLE_ADS_LOGIN_CUSTOMER_ID='1234567890'
```
Then: `source ~/.zshrc`

## Step 4: Add Your Clients (2 minutes)

Edit `~/.hermes/skills/paid-search/_config/client-accounts.json`:

```json
[
  {
    "name": "Nike",
    "aliases": ["nike", "the shoe client"],
    "customer_id": "1234567890",
    "account_lead": "@your-username",
    "slack_channels": ["#nike-paid"],
    "platforms": ["google_ads"]
  }
]
```

Replace with your actual clients and their Google Ads customer IDs.

## Step 5: Set Up Access Control (1 minute)

Edit `~/.hermes/skills/paid-search/_config/access-control.json`:

```json
{
  "admins": ["@your-slack-username"],
  "client_access": {
    "1234567890": ["@teammate1", "@teammate2", "*"]
  }
}
```

## Step 6: Connect Slack + Restart

```bash
hermes integrations slack    # if not already done
hermes restart
```

## Step 7: Test It

In Slack, message your Hermes bot:
- "Is the Nike Q2 campaign on?"
- "What campaigns are running for Nike?"
- "Has the promo been applied to the sale campaign?"

Or test from terminal:
```bash
hermes chat "Is the Nike Q2 campaign enabled?"
```

## What's Working Now

- **Campaign status checks** — ask about any campaign across any client
- **Promo checks** — ask if promotions/extensions are active
- **Slack triage** — messages get classified by urgency
- **FAQ auto-replies** — common questions get answered automatically
- **Thread summaries** — ask to summarize any thread
- **Email drafts** — incoming emails get draft replies
- **Morning digest** — 8:30am daily briefing via Slack DM

## Privacy

Read `config/privacy-policy.md` for the full breakdown, but the TL;DR:
- Campaign data never leaves your machine
- LLM only sees the question + structured result
- Access control prevents cross-client data leakage
- Every query is audit-logged
