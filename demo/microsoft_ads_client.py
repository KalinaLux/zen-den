#!/usr/bin/env python3
"""
Microsoft (Bing) Ads API Client for Zen Den

Handles OAuth2 authentication via Microsoft identity platform and live
campaign data fetching from the Bing Ads / Microsoft Advertising API.
Uses REST endpoints directly — no bingads SDK required.
All data stays local. All connections are read-only.

Setup:
    1. Go to https://portal.azure.com → Azure Active Directory → App
       registrations and create a new registration.
    2. Set the redirect URI to your local callback (e.g.
       http://localhost:5000/callback/microsoft).
    3. Under Certificates & secrets, create a new client secret.
    4. Copy the Application (client) ID, the client secret value, and
       your Directory (tenant) ID.
    5. Sign in at https://ads.microsoft.com and note your Account ID,
       Customer ID, and Developer Token (under Tools → Developer Portal).
    6. In Zen Den settings, enter all credentials and click "Connect"
       to start the OAuth flow.

Usage:
    from microsoft_ads_client import build_oauth_url, exchange_code, fetch_campaigns, sync_all_live_data
"""

import json
import logging
import sys
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("zen.microsoft")

MS_AUTH_BASE = "https://login.microsoftonline.com/common/oauth2/v2.0"
BING_ADS_API = "https://campaign.api.bingads.microsoft.com/Api/Advertiser/CampaignManagement/v13"
BING_REPORTING_API = "https://reporting.api.bingads.microsoft.com/Api/Advertiser/Reporting/v13"

SCOPES = ["https://ads.microsoft.com/msads.manage", "offline_access"]

_STATUS_MAP = {
    "Active": "ENABLED",
    "Paused": "PAUSED",
    "BudgetPaused": "PAUSED",
    "Suspended": "REMOVED",
    "Deleted": "REMOVED",
}


def _data_dir():
    if getattr(sys, '_MEIPASS', None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


DEMO_DIR = _data_dir()
MSADS_CONFIG_PATH = DEMO_DIR / "msads_config.json"
TOKEN_PATH = DEMO_DIR / "msads_tokens.json"


def load_msads_config():
    if MSADS_CONFIG_PATH.exists():
        with open(MSADS_CONFIG_PATH) as f:
            return json.load(f)
    return {
        "client_id": "",
        "client_secret": "",
        "developer_token": "",
        "account_id": "",
        "customer_id": "",
        "connected": False,
        "use_live_data": False,
        "last_sync": None,
    }


def save_msads_config(cfg):
    with open(MSADS_CONFIG_PATH, "w") as f:
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

def build_oauth_url(client_id, redirect_uri):
    """Build the Microsoft OAuth2 consent URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "prompt": "consent",
    }
    return f"{MS_AUTH_BASE}/authorize?{urllib.parse.urlencode(params)}"


def exchange_code(code, client_id, client_secret, redirect_uri):
    """Exchange an authorization code for access + refresh tokens."""
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": " ".join(SCOPES),
    }).encode()
    req = urllib.request.Request(f"{MS_AUTH_BASE}/token", data=data)
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
        "scope": " ".join(SCOPES),
    }).encode()
    req = urllib.request.Request(f"{MS_AUTH_BASE}/token", data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


def get_valid_access_token():
    """Get a valid access token, refreshing if necessary. Returns None if not connected."""
    tokens = load_tokens()
    if not tokens or "refresh_token" not in tokens:
        return None
    cfg = load_msads_config()
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        return None
    try:
        result = refresh_access_token(tokens["refresh_token"], cfg["client_id"], cfg["client_secret"])
        tokens["access_token"] = result["access_token"]
        if "refresh_token" in result:
            tokens["refresh_token"] = result["refresh_token"]
        save_tokens(tokens)
        return result.get("access_token")
    except Exception:
        return None


# ── SOAP helpers ────────────────────────────────────────────────────────────

def _soap_request(url, action, body_xml, developer_token, access_token, account_id=None, customer_id=None):
    """Send a SOAP request to the Bing Ads API."""
    header_parts = [
        f"<DeveloperToken>{developer_token}</DeveloperToken>",
        f"<AuthenticationToken>{access_token}</AuthenticationToken>",
    ]
    if account_id:
        header_parts.append(f"<AccountId>{account_id}</AccountId>")
    if customer_id:
        header_parts.append(f"<CustomerId>{customer_id}</CustomerId>")

    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        "<s:Header>"
        + "".join(header_parts)
        + "</s:Header>"
        "<s:Body>"
        + body_xml
        + "</s:Body>"
        "</s:Envelope>"
    )

    req = urllib.request.Request(url, data=envelope.encode("utf-8"))
    req.add_header("Content-Type", "text/xml; charset=utf-8")
    req.add_header("SOAPAction", action)
    resp = urllib.request.urlopen(req)
    return resp.read().decode("utf-8")


def _extract_between(xml, tag):
    """Naive XML value extractor — pull text between <tag> and </tag>."""
    results = []
    search = f"<{tag}>"
    end_tag = f"</{tag}>"
    start = 0
    while True:
        idx = xml.find(search, start)
        if idx == -1:
            break
        val_start = idx + len(search)
        val_end = xml.find(end_tag, val_start)
        if val_end == -1:
            break
        results.append(xml[val_start:val_end])
        start = val_end + len(end_tag)
    return results


# ── Data fetching ───────────────────────────────────────────────────────────

def fetch_campaigns(access_token, developer_token, account_id, customer_id):
    """Fetch all campaigns for the given Microsoft Ads account.

    Returns a list of campaign dicts in the normalized Zen Den format.
    """
    body = (
        '<GetCampaignsByAccountIdRequest xmlns="https://bingads.microsoft.com/CampaignManagement/v13">'
        f"<AccountId>{account_id}</AccountId>"
        "<CampaignType>Search Shopping Audience</CampaignType>"
        "</GetCampaignsByAccountIdRequest>"
    )
    raw = _soap_request(
        BING_ADS_API + "/CampaignManagementService.svc",
        "GetCampaignsByAccountId",
        body,
        developer_token,
        access_token,
        account_id=account_id,
        customer_id=customer_id,
    )

    ids = _extract_between(raw, "Id")
    names = _extract_between(raw, "Name")
    statuses = _extract_between(raw, "Status")
    budgets = _extract_between(raw, "Amount")

    campaigns = []
    for i in range(len(ids)):
        camp_id = ids[i] if i < len(ids) else ""
        name = names[i] if i < len(names) else ""
        status_raw = statuses[i] if i < len(statuses) else ""
        budget_raw = float(budgets[i]) if i < len(budgets) and budgets[i] else 0.0
        budget_str = f"${budget_raw:.2f}"

        perf = _fetch_campaign_performance(
            camp_id, access_token, developer_token, account_id, customer_id
        )

        campaigns.append({
            "id": camp_id,
            "name": name,
            "status": _STATUS_MAP.get(status_raw, "UNKNOWN"),
            "network": "MICROSOFT",
            "budget_daily": budget_str,
            "start_date": "",
            "end_date": "ongoing",
            "promos": [],
            "performance": perf,
        })

    return campaigns


def _fetch_campaign_performance(campaign_id, access_token, developer_token, account_id, customer_id):
    """Fetch 30-day performance metrics for a single campaign via the Reporting API.

    Falls back to zeroed metrics on any error.
    """
    default = {
        "impressions": 0, "clicks": 0, "ctr": 0.0, "avg_cpc": 0.0,
        "cost": 0.0, "conversions": 0, "conv_rate": 0.0,
        "conv_value": 0.0, "roas": 0.0,
    }

    body = (
        '<SubmitGenerateReportRequest xmlns="https://bingads.microsoft.com/Reporting/v13">'
        "<ReportRequest>"
        "<Format>Csv</Format>"
        "<ReportName>ZenDenPerf</ReportName>"
        "<Time><PredefinedTime>Last30Days</PredefinedTime></Time>"
        "<Filter>"
        f"<CampaignId>{campaign_id}</CampaignId>"
        "</Filter>"
        "<Columns>"
        "<Column>Impressions</Column>"
        "<Column>Clicks</Column>"
        "<Column>Ctr</Column>"
        "<Column>AverageCpc</Column>"
        "<Column>Spend</Column>"
        "<Column>Conversions</Column>"
        "<Column>Revenue</Column>"
        "</Columns>"
        "</ReportRequest>"
        "</SubmitGenerateReportRequest>"
    )

    try:
        raw = _soap_request(
            BING_REPORTING_API + "/ReportingService.svc",
            "SubmitGenerateReport",
            body,
            developer_token,
            access_token,
            account_id=account_id,
            customer_id=customer_id,
        )
        impressions_list = _extract_between(raw, "Impressions")
        clicks_list = _extract_between(raw, "Clicks")
        ctr_list = _extract_between(raw, "Ctr")
        cpc_list = _extract_between(raw, "AverageCpc")
        spend_list = _extract_between(raw, "Spend")
        conv_list = _extract_between(raw, "Conversions")
        rev_list = _extract_between(raw, "Revenue")

        impressions = int(impressions_list[0]) if impressions_list else 0
        clicks = int(clicks_list[0]) if clicks_list else 0
        ctr = float(ctr_list[0]) if ctr_list else 0.0
        avg_cpc = float(cpc_list[0]) if cpc_list else 0.0
        cost = float(spend_list[0]) if spend_list else 0.0
        conversions = int(float(conv_list[0])) if conv_list else 0
        conv_value = float(rev_list[0]) if rev_list else 0.0

        return {
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
        log.warning("Failed to fetch performance for campaign %s: %s", campaign_id, exc)
        return default


def sync_all_live_data():
    """Pull all campaigns from Microsoft Ads.

    Returns (data, error) — data in the same format as mock_campaigns.json.
    """
    cfg = load_msads_config()
    access_token = get_valid_access_token()
    if not access_token:
        return None, "Not authenticated — connect Microsoft Ads first"

    developer_token = cfg.get("developer_token", "")
    account_id = cfg.get("account_id", "")
    customer_id = cfg.get("customer_id", "")
    if not developer_token or not account_id or not customer_id:
        return None, "Missing developer token, account ID, or customer ID in Microsoft Ads configuration"

    try:
        camp_list = fetch_campaigns(access_token, developer_token, account_id, customer_id)
    except Exception as e:
        return None, f"Failed to fetch Microsoft Ads campaigns: {e}"

    client = {
        "name": f"Microsoft Ads ({account_id})",
        "aliases": [],
        "customer_id": account_id,
        "account_lead": "@team",
        "campaigns": camp_list,
    }

    return {"clients": [client]}, None
