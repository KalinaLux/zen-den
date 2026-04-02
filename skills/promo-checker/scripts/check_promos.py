#!/usr/bin/env python3
"""
Promo Checker — queries Google Ads API for promotion extensions,
sitelinks, and ad copy containing promotional language.

Usage:
  python3 check_promos.py --client "Nike" --campaign "Q2 Sale"
  python3 check_promos.py --client "Nike" --list-all
  python3 check_promos.py --client "Nike" --type promotion_extension

Requires:
  pip install google-ads
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = SCRIPT_DIR / "config"
STATE_DIR = Path.home() / ".hermes" / "state"

def load_client_accounts():
    config_path = CONFIG_DIR / "client-accounts.json"
    if not config_path.exists():
        print(json.dumps({"error": f"Config not found: {config_path}"}))
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)

def resolve_client(client_name, accounts):
    from difflib import SequenceMatcher
    client_map = {e["name"]: e for e in accounts}
    best = None
    best_score = 0
    for name in client_map:
        score = SequenceMatcher(None, client_name.lower(), name.lower()).ratio()
        if client_name.lower() in name.lower():
            score = max(score, 0.8)
        if score > best_score:
            best_score = score
            best = name
    if best and best_score >= 0.4:
        return client_map[best], None
    return None, f"No client matching '{client_name}'"

def query_promotion_extensions(customer_id, campaign_name=None):
    """Query promotion extensions from Google Ads."""
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        return [{"error": "google-ads not installed. Run: pip install google-ads"}]

    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    json_key = os.environ.get("GOOGLE_ADS_JSON_KEY_PATH")
    login_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")

    if not all([dev_token, json_key, login_id]):
        return [{"error": "Missing env vars"}]

    config = {
        "developer_token": dev_token,
        "json_key_file_path": json_key,
        "login_customer_id": login_id,
        "impersonated_email": os.environ.get("GOOGLE_ADS_IMPERSONATED_EMAIL"),
    }

    try:
        client = GoogleAdsClient.load_from_dict(config)
        ga_service = client.get_service("GoogleAdsService")
        now = datetime.now(timezone.utc).isoformat()

        # Query promotion extensions
        promo_query = """
            SELECT
                extension_feed_item.promotion_feed_item.promotion_target,
                extension_feed_item.promotion_feed_item.discount_modifier,
                extension_feed_item.promotion_feed_item.percent_off,
                extension_feed_item.promotion_feed_item.money_amount_off.amount_micros,
                extension_feed_item.promotion_feed_item.promotion_code,
                extension_feed_item.promotion_feed_item.promotion_start_date,
                extension_feed_item.promotion_feed_item.promotion_end_date,
                extension_feed_item.status,
                campaign.name,
                campaign.status
            FROM extension_feed_item
            WHERE extension_feed_item.extension_type = 'PROMOTION'
        """

        response = ga_service.search(customer_id=customer_id, query=promo_query)
        promos = []

        for row in response:
            promo = row.extension_feed_item.promotion_feed_item
            entry = {
                "type": "promotion_extension",
                "campaign": row.campaign.name,
                "campaign_status": row.campaign.status.name,
                "extension_status": row.extension_feed_item.status.name,
                "promotion_target": promo.promotion_target,
                "percent_off": promo.percent_off if promo.percent_off else None,
                "money_off": f"${promo.money_amount_off.amount_micros / 1_000_000:.2f}" if promo.money_amount_off.amount_micros else None,
                "promo_code": promo.promotion_code or None,
                "start_date": promo.promotion_start_date or None,
                "end_date": promo.promotion_end_date or None,
                "serving": row.extension_feed_item.status.name == "ENABLED" and row.campaign.status.name == "ENABLED",
                "checked_at": now,
            }
            promos.append(entry)

        if campaign_name:
            from difflib import SequenceMatcher
            filtered = []
            for p in promos:
                score = SequenceMatcher(None, campaign_name.lower(), p["campaign"].lower()).ratio()
                if score >= 0.4 or campaign_name.lower() in p["campaign"].lower():
                    filtered.append(p)
            return filtered

        return promos

    except Exception as e:
        return [{"error": str(e)}]

def log_query(asked_by, client, query_type, result_count, channel="unknown"):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = STATE_DIR / "promo-query-log.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "asked_by": asked_by,
        "client": client,
        "query_type": query_type,
        "result_count": result_count,
        "channel": channel,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

def main():
    parser = argparse.ArgumentParser(description="Check promo/extension status")
    parser.add_argument("--client", required=True)
    parser.add_argument("--campaign", help="Campaign name to filter")
    parser.add_argument("--list-all", action="store_true")
    parser.add_argument("--type", default="all", help="Promo type to check")
    parser.add_argument("--asked-by", default="cli")
    parser.add_argument("--channel", default="cli")
    args = parser.parse_args()

    accounts = load_client_accounts()
    client_entry, err = resolve_client(args.client, accounts)
    if err:
        print(json.dumps({"error": err}))
        sys.exit(1)

    results = query_promotion_extensions(
        client_entry["customer_id"],
        campaign_name=args.campaign if not args.list_all else None,
    )

    for r in results:
        if "error" not in r:
            r["client"] = client_entry["name"]

    log_query(args.asked_by, client_entry["name"], args.type, len(results), args.channel)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
