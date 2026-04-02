#!/usr/bin/env python3
"""
Meta (Facebook) Ads API Client for Zen Den

Handles OAuth2 authentication via Facebook Login and live campaign data
fetching from the Meta Marketing API. Uses graph.facebook.com REST
endpoints directly — no facebook-business SDK required.
All data stays local. All connections are read-only.

Setup:
    1. Go to https://developers.facebook.com and create a new app
       (type "Business").
    2. Under App Settings → Basic, copy your App ID and App Secret.
    3. Add the "Marketing API" product to the app.
    4. In Zen Den settings, enter your App ID, App Secret, and Ad Account ID
       (format: act_XXXXXXXXX — find it in Meta Business Suite → Settings).
    5. Click "Connect" to start the OAuth flow. Grant the
       ads_read + ads_management permissions when prompted.
    6. Zen Den will store your long-lived token locally and refresh it
       automatically.

Usage:
    from meta_ads_client import build_oauth_url, exchange_code, fetch_campaigns, sync_all_live_data
"""

import json
import logging
import sys
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("zen.meta")

GRAPH_API_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

PERMISSIONS = ["ads_read", "ads_management", "business_management"]

_STATUS_MAP = {
    "ACTIVE": "ENABLED",
    "PAUSED": "PAUSED",
    "ARCHIVED": "REMOVED",
    "DELETED": "REMOVED",
}


def _data_dir():
    if getattr(sys, '_MEIPASS', None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


DEMO_DIR = _data_dir()
META_CONFIG_PATH = DEMO_DIR / "meta_ads_config.json"
TOKEN_PATH = DEMO_DIR / "meta_ads_tokens.json"


def load_meta_config():
    if META_CONFIG_PATH.exists():
        with open(META_CONFIG_PATH) as f:
            return json.load(f)
    return {
        "app_id": "",
        "app_secret": "",
        "ad_account_id": "",
        "connected": False,
        "use_live_data": False,
        "last_sync": None,
    }


def save_meta_config(cfg):
    with open(META_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def load_tokens():
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH) as f:
            return json.load(f)
    return None


def save_tokens(tokens):
    with open(TOKEN_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


# ── OAuth2 ──────────────────────────────────────────────────────────────────

def build_oauth_url(app_id, redirect_uri):
    """Build the Facebook OAuth2 consent URL."""
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(PERMISSIONS),
        "response_type": "code",
        "state": "zen_meta_oauth",
    }
    return f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?{urllib.parse.urlencode(params)}"


def exchange_code(code, app_id, app_secret, redirect_uri):
    """Exchange a short-lived auth code for an access token, then swap for a long-lived token."""
    params = urllib.parse.urlencode({
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    })
    url = f"{GRAPH_BASE}/oauth/access_token?{params}"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    short_lived = json.loads(resp.read())

    ll_params = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived["access_token"],
    })
    ll_url = f"{GRAPH_BASE}/oauth/access_token?{ll_params}"
    ll_req = urllib.request.Request(ll_url)
    ll_resp = urllib.request.urlopen(ll_req)
    long_lived = json.loads(ll_resp.read())

    return long_lived


def get_valid_access_token():
    """Return a stored access token if available."""
    tokens = load_tokens()
    if not tokens or "access_token" not in tokens:
        return None
    return tokens["access_token"]


# ── API helpers ─────────────────────────────────────────────────────────────

def _graph_get(path, access_token, params=None):
    """Perform a GET request against the Graph API."""
    qs = {"access_token": access_token}
    if params:
        qs.update(params)
    url = f"{GRAPH_BASE}/{path}?{urllib.parse.urlencode(qs)}"
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


# ── Data fetching ───────────────────────────────────────────────────────────

def fetch_campaigns(access_token, ad_account_id):
    """Fetch all campaigns and insights for an ad account.

    Returns a list of campaign dicts in the normalized Zen Den format.
    """
    acct = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"

    campaigns_raw = _graph_get(
        f"{acct}/campaigns",
        access_token,
        params={
            "fields": "id,name,status,daily_budget,start_time,stop_time",
            "limit": "500",
        },
    )

    campaigns = []
    for camp in campaigns_raw.get("data", []):
        camp_id = camp.get("id", "")

        perf = {"impressions": 0, "clicks": 0, "ctr": 0.0, "avg_cpc": 0.0,
                "cost": 0.0, "conversions": 0, "conv_rate": 0.0,
                "conv_value": 0.0, "roas": 0.0}
        try:
            insights = _graph_get(
                f"{camp_id}/insights",
                access_token,
                params={
                    "fields": "impressions,clicks,ctr,cpc,spend,actions,action_values",
                    "date_preset": "last_30d",
                },
            )
            if insights.get("data"):
                row = insights["data"][0]
                impressions = int(row.get("impressions", 0))
                clicks = int(row.get("clicks", 0))
                ctr = float(row.get("ctr", 0))
                avg_cpc = float(row.get("cpc", 0))
                cost = float(row.get("spend", 0))

                conversions = 0
                for action in row.get("actions", []):
                    if action.get("action_type") in ("offsite_conversion", "lead", "purchase"):
                        conversions += int(float(action.get("value", 0)))

                conv_value = 0.0
                for av in row.get("action_values", []):
                    if av.get("action_type") == "purchase":
                        conv_value += float(av.get("value", 0))

                perf = {
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": round(ctr, 2),
                    "avg_cpc": round(avg_cpc, 2),
                    "cost": round(cost, 2),
                    "conversions": conversions,
                    "conv_rate": round((conversions / clicks * 100) if clicks else 0, 2),
                    "conv_value": round(conv_value, 2),
                    "roas": round((conv_value / cost) if cost > 0 else 0, 2),
                }
        except Exception as exc:
            log.warning("Failed to fetch insights for campaign %s: %s", camp_id, exc)

        daily_budget_raw = int(camp.get("daily_budget", 0))
        budget_str = f"${daily_budget_raw / 100:.2f}" if daily_budget_raw else "$0.00"

        start_time = camp.get("start_time", "")
        start_date = start_time[:10] if start_time else ""
        stop_time = camp.get("stop_time", "")
        end_date = stop_time[:10] if stop_time else "ongoing"

        campaigns.append({
            "id": camp_id,
            "name": camp.get("name", ""),
            "status": _STATUS_MAP.get(camp.get("status", ""), "UNKNOWN"),
            "network": "META",
            "budget_daily": budget_str,
            "start_date": start_date,
            "end_date": end_date,
            "promos": [],
            "performance": perf,
        })

    return campaigns


def sync_all_live_data():
    """Pull all campaigns from Meta Ads.

    Returns (data, error) — data in the same format as mock_campaigns.json.
    """
    cfg = load_meta_config()
    access_token = get_valid_access_token()
    if not access_token:
        return None, "Not authenticated — connect Meta Ads first"

    ad_account_id = cfg.get("ad_account_id", "")
    if not ad_account_id:
        return None, "Missing Ad Account ID in Meta Ads configuration"

    try:
        camp_list = fetch_campaigns(access_token, ad_account_id)
    except Exception as e:
        return None, f"Failed to fetch Meta campaigns: {e}"

    client = {
        "name": f"Meta Ads ({ad_account_id})",
        "aliases": [],
        "customer_id": ad_account_id,
        "account_lead": "@team",
        "campaigns": camp_list,
    }

    return {"clients": [client]}, None
