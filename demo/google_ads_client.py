#!/usr/bin/env python3
"""
Google Ads API Client for Zen Den

Handles OAuth2 authentication and live campaign data fetching.
Uses Google's REST API directly — no google-ads library required.
All data stays local. All connections are read-only.

Usage:
    from google_ads_client import build_oauth_url, exchange_code, fetch_all_clients, fetch_campaigns
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

def _data_dir():
    if getattr(sys, '_MEIPASS', None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent

DEMO_DIR = _data_dir()
TOKEN_PATH = DEMO_DIR / "google_ads_tokens.json"
GADS_CONFIG_PATH = DEMO_DIR / "google_ads_config.json"

SCOPES = ["https://www.googleapis.com/auth/adwords"]
GOOGLE_ADS_API_VERSION = "v17"


def load_gads_config():
    if GADS_CONFIG_PATH.exists():
        with open(GADS_CONFIG_PATH) as f:
            return json.load(f)
    return {
        "client_id": "",
        "client_secret": "",
        "developer_token": "",
        "mcc_customer_id": "",
        "connected": False,
        "use_live_data": False,
        "last_sync": None,
    }


def save_gads_config(cfg):
    with open(GADS_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def load_tokens():
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH) as f:
            return json.load(f)
    return None


def save_tokens(tokens):
    with open(TOKEN_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


def build_oauth_url(client_id, redirect_uri):
    """Build the Google OAuth2 consent URL for the installed-app flow."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


def exchange_code(code, client_id, client_secret, redirect_uri):
    """Exchange an authorization code for access + refresh tokens."""
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def refresh_access_token(refresh_token, client_id, client_secret):
    """Get a fresh access token using a stored refresh token."""
    data = urllib.parse.urlencode({
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def get_valid_access_token():
    """Get a valid access token, refreshing if necessary. Returns None if not connected."""
    tokens = load_tokens()
    if not tokens or "refresh_token" not in tokens:
        return None
    cfg = load_gads_config()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        return None
    try:
        result = refresh_access_token(tokens["refresh_token"], cfg["client_id"], cfg["client_secret"])
        return result.get("access_token")
    except Exception:
        return None


def _gads_search_stream(customer_id, gaql, developer_token, access_token, login_customer_id=None):
    """Execute a GAQL query against the Google Ads searchStream endpoint."""
    clean_id = customer_id.replace("-", "")
    url = f"https://googleads.googleapis.com/{GOOGLE_ADS_API_VERSION}/customers/{clean_id}/googleAds:searchStream"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": developer_token,
        "Content-Type": "application/json",
    }
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id.replace("-", "")
    body = json.dumps({"query": gaql.strip()}).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def fetch_all_clients(developer_token, mcc_customer_id, access_token):
    """Discover all non-manager client accounts under an MCC."""
    gaql = """
    SELECT
        customer_client.client_customer,
        customer_client.descriptive_name,
        customer_client.id,
        customer_client.manager,
        customer_client.status
    FROM customer_client
    WHERE customer_client.manager = false
        AND customer_client.status = 'ENABLED'
    """
    mcc_clean = mcc_customer_id.replace("-", "")
    results = _gads_search_stream(mcc_clean, gaql, developer_token, access_token, login_customer_id=mcc_clean)
    clients = []
    for batch in results:
        for row in batch.get("results", []):
            cc = row.get("customerClient", {})
            clients.append({
                "name": cc.get("descriptiveName", "Unknown"),
                "aliases": [],
                "customer_id": str(cc.get("id", "")),
                "account_lead": "@team",
                "campaigns": [],
            })
    return clients


def fetch_campaigns(customer_id, developer_token, access_token, date_range="LAST_30_DAYS", login_customer_id=None):
    """Fetch all campaigns and metrics for a single client account.

    Returns data in the same format as mock_campaigns.json campaigns list.
    """
    gaql = f"""
    SELECT
        campaign.id, campaign.name, campaign.status,
        campaign.advertising_channel_type,
        campaign_budget.amount_micros,
        campaign.start_date, campaign.end_date,
        metrics.impressions, metrics.clicks, metrics.ctr,
        metrics.average_cpc, metrics.cost_micros,
        metrics.conversions, metrics.conversions_value
    FROM campaign
    WHERE segments.date DURING {date_range}
        AND campaign.status != 'REMOVED'
    ORDER BY metrics.cost_micros DESC
    """
    results = _gads_search_stream(customer_id, gaql, developer_token, access_token, login_customer_id)
    campaigns = []
    for batch in results:
        for row in batch.get("results", []):
            camp = row.get("campaign", {})
            budget = row.get("campaignBudget", {})
            metrics = row.get("metrics", {})

            budget_micros = int(budget.get("amountMicros", 0))
            budget_str = f"${budget_micros / 1_000_000:.2f}" if budget_micros else "$0.00"

            cost_micros = int(metrics.get("costMicros", 0))
            cost = cost_micros / 1_000_000
            avg_cpc_micros = int(metrics.get("averageCpc", 0))
            avg_cpc = avg_cpc_micros / 1_000_000
            clicks = int(metrics.get("clicks", 0))
            impressions = int(metrics.get("impressions", 0))
            conversions = float(metrics.get("conversions", 0))
            conv_value = float(metrics.get("conversionsValue", 0))
            ctr = float(metrics.get("ctr", 0)) * 100

            end_date = camp.get("endDate", "")
            if end_date == "2037-12-30":
                end_date = "ongoing"

            campaigns.append({
                "id": str(camp.get("id", "")),
                "name": camp.get("name", ""),
                "status": camp.get("status", "UNKNOWN"),
                "network": camp.get("advertisingChannelType", "SEARCH"),
                "budget_daily": budget_str,
                "start_date": camp.get("startDate", ""),
                "end_date": end_date,
                "promos": [],
                "performance": {
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": round(ctr, 2),
                    "avg_cpc": round(avg_cpc, 2),
                    "cost": round(cost, 2),
                    "conversions": int(conversions),
                    "conv_rate": round((conversions / clicks * 100) if clicks else 0, 2),
                    "conv_value": round(conv_value, 2),
                    "roas": round((conv_value / cost) if cost > 0 else 0, 2),
                },
            })
    return campaigns


def sync_all_live_data():
    """Pull all client accounts and their campaigns from Google Ads.

    Returns data in the same format as mock_campaigns.json.
    """
    cfg = load_gads_config()
    access_token = get_valid_access_token()
    if not access_token:
        return None, "Not authenticated — connect Google Ads first"
    developer_token = cfg.get("developer_token", "")
    mcc_id = cfg.get("mcc_customer_id", "")
    if not developer_token or not mcc_id:
        return None, "Missing developer token or MCC customer ID"

    try:
        clients = fetch_all_clients(developer_token, mcc_id, access_token)
    except Exception as e:
        return None, f"Failed to fetch client list: {e}"

    mcc_clean = mcc_id.replace("-", "")
    for client in clients:
        try:
            client["campaigns"] = fetch_campaigns(
                client["customer_id"], developer_token, access_token,
                login_customer_id=mcc_clean,
            )
        except Exception as e:
            client["campaigns"] = []
            client["_sync_error"] = str(e)

    return {"clients": clients}, None
