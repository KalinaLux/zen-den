#!/usr/bin/env python3
"""
Campaign Status Checker — queries Google Ads API for campaign status.
Runs locally. All data stays on this machine.

Usage:
  python3 check_campaign.py --client "Nike" --campaign "Q2 Awareness"
  python3 check_campaign.py --client "Nike" --list-all
  python3 check_campaign.py --search "black friday"

Requires:
  pip install google-ads
  Environment vars: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_JSON_KEY_PATH, GOOGLE_ADS_LOGIN_CUSTOMER_ID
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher

SCRIPT_DIR = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = SCRIPT_DIR / "config"
STATE_DIR = Path.home() / ".hermes" / "state"

def load_client_accounts():
    config_path = CONFIG_DIR / "client-accounts.json"
    if not config_path.exists():
        print(json.dumps({"error": f"Client accounts config not found at {config_path}"}))
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)

def fuzzy_match(query, candidates, threshold=0.4):
    """Return candidates that fuzzy-match the query, sorted by similarity."""
    query_lower = query.lower()
    results = []
    for candidate in candidates:
        ratio = SequenceMatcher(None, query_lower, candidate.lower()).ratio()
        if ratio >= threshold or query_lower in candidate.lower():
            results.append((candidate, ratio))
    return sorted(results, key=lambda x: x[1], reverse=True)

def resolve_client(client_name, accounts):
    """Find the client account ID from a fuzzy client name."""
    client_map = {entry["name"]: entry for entry in accounts}
    matches = fuzzy_match(client_name, client_map.keys(), threshold=0.5)
    if not matches:
        return None, f"No client found matching '{client_name}'. Available: {', '.join(client_map.keys())}"
    best_name = matches[0][0]
    return client_map[best_name], None

def check_access(slack_user, client_id):
    """Verify the Slack user is authorized to query this client's data."""
    acl_path = CONFIG_DIR / "access-control.json"
    if not acl_path.exists():
        return True  # no ACL file = open access (warn in logs)
    with open(acl_path) as f:
        acl = json.load(f)
    if slack_user in acl.get("admins", []):
        return True
    client_users = acl.get("client_access", {}).get(client_id, [])
    return slack_user in client_users or "*" in client_users

def query_google_ads(customer_id, campaign_query=None, list_all=False):
    """
    Query Google Ads API for campaign status.
    Returns list of campaign dicts.
    """
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        return [{
            "error": "google-ads package not installed. Run: pip install google-ads",
            "fallback": True
        }]

    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    json_key = os.environ.get("GOOGLE_ADS_JSON_KEY_PATH")
    login_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")

    if not all([dev_token, json_key, login_id]):
        return [{"error": "Missing environment variables. Need: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_JSON_KEY_PATH, GOOGLE_ADS_LOGIN_CUSTOMER_ID"}]

    config = {
        "developer_token": dev_token,
        "json_key_file_path": json_key,
        "login_customer_id": login_id,
        "impersonated_email": os.environ.get("GOOGLE_ADS_IMPERSONATED_EMAIL"),
    }

    try:
        client = GoogleAdsClient.load_from_dict(config)
        ga_service = client.get_service("GoogleAdsService")

        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign.start_date,
                campaign.end_date,
                campaign_budget.amount_micros
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            ORDER BY campaign.name
        """

        response = ga_service.search(customer_id=customer_id, query=query)
        campaigns = []
        now = datetime.now(timezone.utc).isoformat()

        for row in response:
            camp = {
                "id": str(row.campaign.id),
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "network": row.campaign.advertising_channel_type.name,
                "start_date": row.campaign.start_date,
                "end_date": row.campaign.end_date or "ongoing",
                "budget_micros": row.campaign_budget.amount_micros,
                "budget_daily": f"${row.campaign_budget.amount_micros / 1_000_000:.2f}",
                "checked_at": now,
            }
            campaigns.append(camp)

        if list_all:
            return campaigns

        if campaign_query:
            names = [c["name"] for c in campaigns]
            matches = fuzzy_match(campaign_query, names)
            matched_names = {m[0] for m in matches}
            return [c for c in campaigns if c["name"] in matched_names]

        return campaigns

    except Exception as e:
        return [{"error": str(e)}]

def log_query(asked_by, client, campaign, result, channel="unknown"):
    """Append audit log entry."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = STATE_DIR / "campaign-query-log.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "asked_by": asked_by,
        "client": client,
        "campaign": campaign,
        "result_count": len(result) if isinstance(result, list) else 1,
        "channel": channel,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Check Google Ads campaign status")
    parser.add_argument("--client", help="Client name to look up")
    parser.add_argument("--campaign", help="Campaign name or keyword to search")
    parser.add_argument("--list-all", action="store_true", help="List all campaigns for client")
    parser.add_argument("--search", help="Search campaign name across all clients")
    parser.add_argument("--asked-by", default="cli", help="Who is asking (for audit log)")
    parser.add_argument("--channel", default="cli", help="Slack channel (for audit log)")
    args = parser.parse_args()

    accounts = load_client_accounts()

    if args.search:
        all_results = []
        for acct in accounts:
            campaigns = query_google_ads(acct["customer_id"], campaign_query=args.search)
            for c in campaigns:
                if "error" not in c:
                    c["client"] = acct["name"]
            all_results.extend(campaigns)
        log_query(args.asked_by, "ALL", args.search, all_results, args.channel)
        print(json.dumps(all_results, indent=2))
        return

    if not args.client:
        parser.error("--client is required unless using --search")

    client_entry, err = resolve_client(args.client, accounts)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    if not check_access(args.asked_by, client_entry["customer_id"]):
        print(json.dumps({
            "error": "access_denied",
            "message": f"User {args.asked_by} is not authorized to query {client_entry['name']}",
            "contact": client_entry.get("account_lead", "your account lead")
        }))
        sys.exit(1)

    results = query_google_ads(
        client_entry["customer_id"],
        campaign_query=args.campaign,
        list_all=args.list_all,
    )

    for r in results:
        if "error" not in r:
            r["client"] = client_entry["name"]

    log_query(args.asked_by, client_entry["name"], args.campaign or "ALL", results, args.channel)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
