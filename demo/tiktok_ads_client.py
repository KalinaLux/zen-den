#!/usr/bin/env python3
"""
TikTok Ads API Client for Zen Den

Handles OAuth2 authentication and live campaign data fetching from the
TikTok Marketing API. Uses REST endpoints directly — no tiktok-business-api
SDK required. All data stays local. All connections are read-only.

Setup:
    1. Go to https://ads.tiktok.com/marketing_api/ and create a developer
       app. Select "CMP API" as the product.
    2. Under App Management, copy your App ID and Secret.
    3. Submit the app for review (TikTok requires approval for Marketing
       API access).
    4. Once approved, note your Advertiser ID from TikTok Ads Manager
       (the numeric ID shown in the top-right of the dashboard).
    5. In Zen Den settings, enter your App ID, Secret, and Advertiser ID,
       then click "Connect" to start the OAuth flow.
    6. Authorize the app when prompted. Zen Den stores the access token
       locally.

Usage:
    from tiktok_ads_client import build_oauth_url, exchange_code, fetch_campaigns, sync_all_live_data
"""

import json
import logging
import sys
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("zen.tiktok")

TIKTOK_AUTH_BASE = "https://business-api.tiktok.com/portal/auth"
TIKTOK_API_BASE = "https://business-api.tiktok.com/open_api/v1.3"

_STATUS_MAP = {
    "CAMPAIGN_STATUS_ENABLE": "ENABLED",
    "CAMPAIGN_STATUS_DISABLE": "PAUSED",
    "CAMPAIGN_STATUS_DELETE": "REMOVED",
    "CAMPAIGN_STATUS_BUDGET_EXCEED": "PAUSED",
    "CAMPAIGN_STATUS_NOT_DELETE": "ENABLED",
    "ENABLE": "ENABLED",
    "DISABLE": "PAUSED",
    "DELETE": "REMOVED",
}


def _data_dir():
    if getattr(sys, '_MEIPASS', None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


DEMO_DIR = _data_dir()
TIKTOK_CONFIG_PATH = DEMO_DIR / "tiktok_ads_config.json"
TOKEN_PATH = DEMO_DIR / "tiktok_ads_tokens.json"


def load_tiktok_config():
    if TIKTOK_CONFIG_PATH.exists():
        with open(TIKTOK_CONFIG_PATH) as f:
            return json.load(f)
    return {
        "app_id": "",
        "app_secret": "",
        "advertiser_id": "",
        "connected": False,
        "use_live_data": False,
        "last_sync": None,
    }


def save_tiktok_config(cfg):
    with open(TIKTOK_CONFIG_PATH, "w") as f:
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
    """Build the TikTok OAuth2 consent URL."""
    params = {
        "app_id": app_id,
        "redirect_uri": redirect_uri,
        "state": "zen_tiktok_oauth",
    }
    return f"{TIKTOK_AUTH_BASE}?{urllib.parse.urlencode(params)}"


def exchange_code(code, app_id, app_secret, redirect_uri):
    """Exchange an authorization code for an access token."""
    payload = json.dumps({
        "app_id": app_id,
        "secret": app_secret,
        "auth_code": code,
    }).encode()
    req = urllib.request.Request(
        f"{TIKTOK_API_BASE}/oauth2/access_token/",
        data=payload,
    )
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())

    if result.get("code") != 0:
        raise RuntimeError(f"TikTok token exchange failed: {result.get('message', 'unknown error')}")

    return result.get("data", {})


def get_valid_access_token():
    """Return a stored access token if available."""
    tokens = load_tokens()
    if not tokens or "access_token" not in tokens:
        return None
    return tokens["access_token"]


# ── API helpers ─────────────────────────────────────────────────────────────

def _tiktok_get(path, access_token, params=None):
    """Perform a GET request against the TikTok Marketing API."""
    qs = params or {}
    url = f"{TIKTOK_API_BASE}/{path}?{urllib.parse.urlencode(qs)}"
    req = urllib.request.Request(url)
    req.add_header("Access-Token", access_token)
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    if result.get("code") != 0:
        raise RuntimeError(f"TikTok API error: {result.get('message', 'unknown')}")
    return result.get("data", {})


def _tiktok_post(path, access_token, body):
    """Perform a POST request against the TikTok Marketing API."""
    payload = json.dumps(body).encode()
    url = f"{TIKTOK_API_BASE}/{path}"
    req = urllib.request.Request(url, data=payload)
    req.add_header("Content-Type", "application/json")
    req.add_header("Access-Token", access_token)
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    if result.get("code") != 0:
        raise RuntimeError(f"TikTok API error: {result.get('message', 'unknown')}")
    return result.get("data", {})


# ── Data fetching ───────────────────────────────────────────────────────────

def fetch_campaigns(access_token, advertiser_id):
    """Fetch all campaigns and metrics for a TikTok advertiser.

    Returns a list of campaign dicts in the normalized Zen Den format.
    """
    data = _tiktok_get(
        "campaign/get/",
        access_token,
        params={
            "advertiser_id": advertiser_id,
            "page_size": "1000",
        },
    )

    campaign_ids = []
    campaigns_by_id = {}
    for camp in data.get("list", []):
        cid = str(camp.get("campaign_id", ""))
        campaign_ids.append(cid)

        budget_raw = float(camp.get("budget", 0))
        budget_str = f"${budget_raw:.2f}" if budget_raw else "$0.00"

        status_raw = camp.get("operation_status", camp.get("status", ""))

        campaigns_by_id[cid] = {
            "id": cid,
            "name": camp.get("campaign_name", ""),
            "status": _STATUS_MAP.get(status_raw, "UNKNOWN"),
            "network": "TIKTOK",
            "budget_daily": budget_str,
            "start_date": "",
            "end_date": "ongoing",
            "promos": [],
            "performance": {
                "impressions": 0, "clicks": 0, "ctr": 0.0, "avg_cpc": 0.0,
                "cost": 0.0, "conversions": 0, "conv_rate": 0.0,
                "conv_value": 0.0, "roas": 0.0,
            },
        }

    if campaign_ids:
        try:
            _populate_performance(access_token, advertiser_id, campaign_ids, campaigns_by_id)
        except Exception as exc:
            log.warning("Failed to fetch TikTok campaign metrics: %s", exc)

    return list(campaigns_by_id.values())


def _populate_performance(access_token, advertiser_id, campaign_ids, campaigns_by_id):
    """Fetch aggregated 30-day metrics for a batch of campaigns."""
    report = _tiktok_post(
        "report/integrated/get/",
        access_token,
        body={
            "advertiser_id": advertiser_id,
            "report_type": "BASIC",
            "dimensions": ["campaign_id"],
            "data_level": "AUCTION_CAMPAIGN",
            "metrics": [
                "spend", "impressions", "clicks", "ctr", "cpc",
                "conversion", "cost_per_conversion", "total_complete_payment_rate",
                "complete_payment", "total_purchase_value",
            ],
            "start_date": "",
            "end_date": "",
            "lifetime": False,
            "page_size": 1000,
            "filters": [
                {"field_name": "campaign_ids", "filter_type": "IN", "filter_value": json.dumps(campaign_ids)},
            ],
        },
    )

    for row in report.get("list", []):
        dims = row.get("dimensions", {})
        metrics = row.get("metrics", {})
        cid = str(dims.get("campaign_id", ""))
        if cid not in campaigns_by_id:
            continue

        impressions = int(float(metrics.get("impressions", 0)))
        clicks = int(float(metrics.get("clicks", 0)))
        ctr = float(metrics.get("ctr", 0))
        avg_cpc = float(metrics.get("cpc", 0))
        cost = float(metrics.get("spend", 0))
        conversions = int(float(metrics.get("conversion", 0)))
        conv_value = float(metrics.get("total_purchase_value", 0))

        campaigns_by_id[cid]["performance"] = {
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(ctr * 100, 2),
            "avg_cpc": round(avg_cpc, 2),
            "cost": round(cost, 2),
            "conversions": conversions,
            "conv_rate": round((conversions / clicks * 100) if clicks else 0, 2),
            "conv_value": round(conv_value, 2),
            "roas": round((conv_value / cost) if cost > 0 else 0, 2),
        }


def sync_all_live_data():
    """Pull all campaigns from TikTok Ads.

    Returns (data, error) — data in the same format as mock_campaigns.json.
    """
    cfg = load_tiktok_config()
    access_token = get_valid_access_token()
    if not access_token:
        return None, "Not authenticated — connect TikTok Ads first"

    advertiser_id = cfg.get("advertiser_id", "")
    if not advertiser_id:
        return None, "Missing Advertiser ID in TikTok Ads configuration"

    try:
        camp_list = fetch_campaigns(access_token, advertiser_id)
    except Exception as e:
        return None, f"Failed to fetch TikTok campaigns: {e}"

    client = {
        "name": f"TikTok Ads ({advertiser_id})",
        "aliases": [],
        "customer_id": advertiser_id,
        "account_lead": "@team",
        "campaigns": camp_list,
    }

    return {"clients": [client]}, None
