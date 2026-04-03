"""Zen Den — Ad Creative Management Module

Create, edit, version, AI-generate copy, and push creatives to ad platforms.
Follows a DRAFT-FIRST workflow: nothing goes live without explicit human
approval.

Usage:
    from creative_manager import (
        load_creatives, create_creative, update_creative,
        approve_creative, push_creative, generate_variations,
    )
"""

import copy
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("zen.creatives")

# ---------------------------------------------------------------------------
# Data directory resolution (PyInstaller-aware)
# ---------------------------------------------------------------------------

def _data_dir():
    if getattr(sys, "_MEIPASS", None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


CREATIVES_PATH = _data_dir() / "creatives.json"

VALID_STATUSES = ("draft", "review", "approved", "live", "paused", "archived")
VALID_PLATFORMS = ("GOOGLE", "META", "MICROSOFT", "TIKTOK")
VALID_AD_TYPES = ("responsive_search", "display", "social_post", "video_script")

PLATFORM_CONSTRAINTS = {
    "GOOGLE": {
        "max_headlines": 15,
        "headline_chars": 30,
        "max_descriptions": 4,
        "description_chars": 90,
    },
    "META": {
        "primary_text_chars": 125,
        "headline_chars": 40,
        "description_chars": 30,
    },
    "MICROSOFT": {
        "max_headlines": 15,
        "headline_chars": 30,
        "max_descriptions": 4,
        "description_chars": 90,
    },
    "TIKTOK": {
        "ad_text_chars": 100,
        "ctas": [
            "Shop Now", "Learn More", "Sign Up", "Download",
            "Contact Us", "Apply Now", "Book Now", "Get Quote",
        ],
    },
}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_creatives() -> dict:
    """Load the full creatives data structure; seed demo data if missing."""
    if not CREATIVES_PATH.exists():
        seed_demo_creatives()
    try:
        return json.loads(CREATIVES_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.exception("Failed to load creatives from %s", CREATIVES_PATH)
        return {"creatives": [], "push_log": []}


def save_creatives(data: dict):
    """Persist creatives data to disk."""
    try:
        CREATIVES_PATH.parent.mkdir(parents=True, exist_ok=True)
        CREATIVES_PATH.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        log.exception("Failed to save creatives to %s", CREATIVES_PATH)


def get_creative(creative_id: str) -> dict | None:
    """Return a single creative by ID, or None."""
    for c in load_creatives().get("creatives", []):
        if c.get("id") == creative_id:
            return c
    return None


def list_creatives(
    client_name: str = None,
    campaign_id: str = None,
    status: str = None,
    platform: str = None,
) -> list:
    """Filter creatives by any combination of fields."""
    results = load_creatives().get("creatives", [])
    if client_name:
        results = [c for c in results if c.get("client_name") == client_name]
    if campaign_id:
        results = [c for c in results if c.get("campaign_id") == campaign_id]
    if status:
        results = [c for c in results if c.get("status") == status]
    if platform:
        results = [c for c in results if c.get("platform") == platform]
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_id() -> str:
    return f"cr_{int(time.time())}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _snapshot(creative: dict, note: str = "") -> dict:
    """Create a version snapshot of headline/description state."""
    return {
        "version": creative.get("version", 1),
        "timestamp": _now(),
        "headlines": list(creative.get("headlines") or []),
        "descriptions": list(creative.get("descriptions") or []),
        "change_note": note or "Update",
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_creative(creative: dict) -> dict:
    """Add a new creative.  Auto-generates ID, timestamps, version 1."""
    try:
        data = load_creatives()
        now = _now()
        creative.setdefault("id", _gen_id())
        creative.setdefault("status", "draft")
        creative.setdefault("created", now)
        creative.setdefault("modified", now)
        creative.setdefault("approved_at", None)
        creative.setdefault("pushed_at", None)
        creative.setdefault("approved_by", None)
        creative.setdefault("version", 1)
        creative.setdefault("performance", None)
        creative.setdefault("image_url", None)
        creative.setdefault("video_url", None)
        creative.setdefault("tags", [])
        creative["versions"] = [
            _snapshot(creative, "Initial draft")
        ]
        data["creatives"].append(creative)
        save_creatives(data)
        log.info("Created creative %s for %s", creative["id"], creative.get("client_name"))
        return creative
    except Exception:
        log.exception("Failed to create creative")
        return creative


def update_creative(creative_id: str, updates: dict) -> dict | None:
    """Apply updates to a creative, bump version, archive old state."""
    try:
        data = load_creatives()
        for c in data["creatives"]:
            if c["id"] != creative_id:
                continue

            old_version = _snapshot(c, updates.pop("change_note", "Edit"))
            c.get("versions", []).append(old_version)

            for key, val in updates.items():
                if key not in ("id", "created", "versions"):
                    c[key] = val

            c["version"] = c.get("version", 1) + 1
            c["modified"] = _now()
            save_creatives(data)
            log.info("Updated creative %s to v%s", creative_id, c["version"])
            return c
        return None
    except Exception:
        log.exception("Failed to update creative %s", creative_id)
        return None


def delete_creative(creative_id: str) -> bool:
    """Remove a creative from the store."""
    try:
        data = load_creatives()
        before = len(data["creatives"])
        data["creatives"] = [c for c in data["creatives"] if c["id"] != creative_id]
        if len(data["creatives"]) < before:
            save_creatives(data)
            log.info("Deleted creative %s", creative_id)
            return True
        return False
    except Exception:
        log.exception("Failed to delete creative %s", creative_id)
        return False


def duplicate_creative(creative_id: str) -> dict | None:
    """Clone a creative with a new ID and reset it to draft."""
    try:
        original = get_creative(creative_id)
        if not original:
            return None
        dup = copy.deepcopy(original)
        dup["id"] = _gen_id()
        dup["status"] = "draft"
        dup["created"] = _now()
        dup["modified"] = _now()
        dup["approved_at"] = None
        dup["pushed_at"] = None
        dup["approved_by"] = None
        dup["version"] = 1
        dup["versions"] = [_snapshot(dup, f"Duplicated from {creative_id}")]
        dup["performance"] = None

        data = load_creatives()
        data["creatives"].append(dup)
        save_creatives(data)
        log.info("Duplicated %s → %s", creative_id, dup["id"])
        return dup
    except Exception:
        log.exception("Failed to duplicate creative %s", creative_id)
        return None


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

def submit_for_review(creative_id: str) -> dict | None:
    """Move a draft creative into review status."""
    try:
        data = load_creatives()
        for c in data["creatives"]:
            if c["id"] == creative_id:
                if c["status"] != "draft":
                    log.warning("Cannot submit %s — status is %s", creative_id, c["status"])
                    return None
                c["status"] = "review"
                c["modified"] = _now()
                save_creatives(data)
                log.info("Creative %s submitted for review", creative_id)
                return c
        return None
    except Exception:
        log.exception("Failed to submit creative %s for review", creative_id)
        return None


def approve_creative(creative_id: str, approved_by: str = "user") -> dict | None:
    """Approve a creative that is in review.  Records who approved and when."""
    try:
        data = load_creatives()
        for c in data["creatives"]:
            if c["id"] == creative_id:
                if c["status"] not in ("review", "draft"):
                    log.warning("Cannot approve %s — status is %s", creative_id, c["status"])
                    return None
                c["status"] = "approved"
                c["approved_at"] = _now()
                c["approved_by"] = approved_by
                c["modified"] = _now()
                save_creatives(data)
                log.info("Creative %s approved by %s", creative_id, approved_by)
                return c
        return None
    except Exception:
        log.exception("Failed to approve creative %s", creative_id)
        return None


def reject_creative(creative_id: str, reason: str = "") -> dict | None:
    """Send a creative back to draft with an optional rejection reason."""
    try:
        data = load_creatives()
        for c in data["creatives"]:
            if c["id"] == creative_id:
                if c["status"] not in ("review", "approved"):
                    log.warning("Cannot reject %s — status is %s", creative_id, c["status"])
                    return None
                c["status"] = "draft"
                c["modified"] = _now()
                c["approved_at"] = None
                c["approved_by"] = None
                note = f"Rejected: {reason}" if reason else "Rejected"
                c.setdefault("versions", []).append(_snapshot(c, note))
                save_creatives(data)
                log.info("Creative %s rejected: %s", creative_id, reason or "(no reason)")
                return c
        return None
    except Exception:
        log.exception("Failed to reject creative %s", creative_id)
        return None


def rollback_creative(creative_id: str, version: int) -> dict | None:
    """Restore a creative to a previous version's headlines and descriptions."""
    try:
        data = load_creatives()
        for c in data["creatives"]:
            if c["id"] != creative_id:
                continue
            target = None
            for v in c.get("versions", []):
                if v.get("version") == version:
                    target = v
                    break
            if not target:
                log.warning("Version %d not found for %s", version, creative_id)
                return None

            c.get("versions", []).append(
                _snapshot(c, f"Pre-rollback snapshot (was v{c['version']})")
            )
            c["headlines"] = list(target.get("headlines", []))
            c["descriptions"] = list(target.get("descriptions", []))
            c["version"] = c.get("version", 1) + 1
            c["modified"] = _now()
            c["status"] = "draft"
            c.get("versions", []).append(
                _snapshot(c, f"Rolled back to v{version}")
            )
            save_creatives(data)
            log.info("Rolled back %s to v%d (now v%d)", creative_id, version, c["version"])
            return c
        return None
    except Exception:
        log.exception("Failed to rollback creative %s", creative_id)
        return None


# ---------------------------------------------------------------------------
# AI Copy Generation
# ---------------------------------------------------------------------------

def generate_copy_prompt(params: dict) -> str:
    """Build a detailed prompt instructing an AI to generate ad copy.

    Expected *params* keys:
        platform, ad_type, client_name, product_description,
        target_audience, tone, keywords (list), constraints (dict),
        existing_copy (dict|None), goal
    """
    platform = params.get("platform", "GOOGLE").upper()
    ad_type = params.get("ad_type", "responsive_search")
    client = params.get("client_name", "the brand")
    product = params.get("product_description", "")
    audience = params.get("target_audience", "general consumers")
    tone = params.get("tone", "professional")
    keywords = params.get("keywords", [])
    goal = params.get("goal", "conversions")
    existing = params.get("existing_copy")

    constraints = PLATFORM_CONSTRAINTS.get(platform, {})
    user_constraints = params.get("constraints") or {}
    constraints.update(user_constraints)

    lines = [
        f"You are an expert digital advertising copywriter.",
        f"",
        f"Write ad copy for **{client}** on **{platform}** ({ad_type}).",
        f"",
        f"Product/service: {product}" if product else "",
        f"Target audience: {audience}",
        f"Tone: {tone}",
        f"Campaign goal: {goal}",
    ]

    if keywords:
        lines.append(f"Target keywords: {', '.join(keywords)}")

    lines.append("")
    lines.append("## Platform constraints")

    if platform in ("GOOGLE", "MICROSOFT"):
        lines.append(f"- Up to {constraints.get('max_headlines', 15)} headlines, "
                      f"max {constraints.get('headline_chars', 30)} characters each")
        lines.append(f"- Up to {constraints.get('max_descriptions', 4)} descriptions, "
                      f"max {constraints.get('description_chars', 90)} characters each")
        lines.append("- Each headline must be unique and compelling")
        lines.append("- Include keywords naturally in at least 3 headlines")
    elif platform == "META":
        lines.append(f"- Primary text: max {constraints.get('primary_text_chars', 125)} characters")
        lines.append(f"- Headline: max {constraints.get('headline_chars', 40)} characters")
        lines.append(f"- Link description: max {constraints.get('description_chars', 30)} characters")
        lines.append("- Tone should be conversational and scroll-stopping")
    elif platform == "TIKTOK":
        lines.append(f"- Ad text: max {constraints.get('ad_text_chars', 100)} characters")
        ctas = constraints.get("ctas", PLATFORM_CONSTRAINTS["TIKTOK"]["ctas"])
        lines.append(f"- CTA must be one of: {', '.join(ctas)}")
        lines.append("- Copy should feel native to TikTok — casual, punchy, Gen-Z friendly")

    if existing:
        lines.append("")
        lines.append("## Existing copy to improve/vary")
        lines.append(json.dumps(existing, indent=2))

    lines.append("")
    lines.append("## Output format")
    lines.append("Return ONLY valid JSON with this structure:")
    lines.append('{"headlines": ["..."], "descriptions": ["..."], "cta": "..."}')
    lines.append("")
    lines.append("Do not include any explanation outside the JSON object.")

    return "\n".join(line for line in lines)


def generate_placeholder_copy(params: dict) -> dict:
    """Generate reasonable placeholder copy when no AI API is available."""
    platform = params.get("platform", "GOOGLE").upper()
    client = params.get("client_name", "Your Brand")
    product = params.get("product_description", "amazing products")
    tone = params.get("tone", "professional")
    goal = params.get("goal", "conversions")
    keywords = params.get("keywords", [])

    short_product = product[:25] if len(product) > 25 else product

    if platform in ("GOOGLE", "MICROSOFT"):
        headlines = [
            f"Shop {client} Today",
            f"Premium {short_product}",
            f"Get 20% Off First Order",
            f"Free Shipping Over $50",
            f"{client} — Official Site",
        ]
        if keywords:
            for kw in keywords[:3]:
                headlines.append(f"{kw.title()} — {client}"[:30])

        descs = [
            f"Discover {client}'s top-rated {short_product}. Free shipping on orders over $50.",
            f"Join thousands of happy customers. Shop {client} now and save.",
        ]
        cta = "Shop Now" if goal == "conversions" else "Learn More"

    elif platform == "META":
        headlines = [
            f"Love your {short_product}",
            f"{client} has arrived",
        ]
        descs = [
            f"Treat yourself to something special from {client}. "
            f"Tap to discover our best sellers.",
        ]
        cta = "Shop Now"

    elif platform == "TIKTOK":
        headlines = [f"{client} just dropped something 🔥"]
        descs = [
            f"POV: you finally found {short_product} that actually works. Link in bio."
        ]
        valid_ctas = PLATFORM_CONSTRAINTS["TIKTOK"]["ctas"]
        cta = "Shop Now" if "Shop Now" in valid_ctas else valid_ctas[0]

    else:
        headlines = [f"Discover {client}"]
        descs = [f"Learn more about {client}'s {short_product}."]
        cta = "Learn More"

    return {"headlines": headlines, "descriptions": descs, "cta": cta}


def generate_variations(creative_id: str, count: int = 3) -> list[dict]:
    """Generate *count* variations of an existing creative using placeholder logic."""
    original = get_creative(creative_id)
    if not original:
        return []

    base_params = {
        "platform": original.get("platform", "GOOGLE"),
        "client_name": original.get("client_name", "Brand"),
        "product_description": " ".join(original.get("descriptions") or ["products"]),
        "keywords": original.get("tags", []),
        "goal": "conversions",
    }

    prefixes = [
        ("Try", "New", "Best"),
        ("Top", "Your", "Save on"),
        ("Discover", "Premium", "Limited"),
        ("Exclusive", "Shop", "Love"),
    ]
    verbs = ["Discover", "Experience", "Unlock", "Enjoy"]
    suffixes = ["today", "now", "this week", "— limited time"]

    variations = []
    for i in range(count):
        var = generate_placeholder_copy(base_params)

        prefix_set = prefixes[i % len(prefixes)]
        verb = verbs[i % len(verbs)]
        suffix = suffixes[i % len(suffixes)]
        client = base_params["client_name"]

        extra_headlines = [
            f"{prefix_set[0]} {client} {suffix}"[:30],
            f"{prefix_set[1]} — {client}"[:30],
            f"{verb} {client} {suffix}"[:30],
        ]
        var["headlines"] = (var["headlines"] + extra_headlines)[:15]

        extra_desc = (
            f"{verb} what {client} has to offer. "
            f"Order {suffix} and get free shipping."
        )[:90]
        var["descriptions"].append(extra_desc)
        var["descriptions"] = var["descriptions"][:4]

        var["variation_index"] = i + 1
        variations.append(var)

    return variations


# ---------------------------------------------------------------------------
# Platform Push (stubs)
# ---------------------------------------------------------------------------

def push_to_google(creative: dict, config: dict = None) -> dict:
    """Push a creative to Google Ads.

    In production this would call the Google Ads API v17:

        client = GoogleAdsClient.load_from_storage()
        service = client.get_service("GoogleAdsService")
        ad_group_ad_op = client.get_type("AdGroupAdOperation")
        ad = ad_group_ad_op.create.ad
        ad.responsive_search_ad.headlines = [
            {"text": h, "pinned_field": None} for h in creative["headlines"]
        ]
        ad.responsive_search_ad.descriptions = [
            {"text": d} for d in creative["descriptions"]
        ]
        ad.final_urls.append(creative["final_url"])
        response = service.mutate(
            customer_id=config["customer_id"],
            mutate_operations=[MutateOperation(ad_group_ad_operation=ad_group_ad_op)],
        )

    Returns a result dict indicating success or failure.
    """
    platform_id = f"gads_{int(time.time())}"
    log.info("[STUB] Pushed creative %s to Google Ads → %s", creative.get("id"), platform_id)
    return {
        "success": True,
        "platform": "GOOGLE",
        "platform_id": platform_id,
        "message": f"Ad created in campaign {creative.get('campaign_id', 'unknown')}",
    }


def push_to_meta(creative: dict, config: dict = None) -> dict:
    """Push a creative to Meta (Facebook/Instagram) Ads.

    In production this would call the Meta Marketing API:

        POST https://graph.facebook.com/v19.0/{ad_account_id}/ads
        Body: {
            "name": creative["campaign_name"],
            "adset_id": config["adset_id"],
            "creative": {
                "title": creative["headlines"][0],
                "body": creative["descriptions"][0],
                "link_url": creative["final_url"],
                "call_to_action_type": creative["cta"].upper().replace(" ", "_"),
                "image_hash": creative.get("image_url"),
            },
            "status": "PAUSED",
        }

    Returns a result dict indicating success or failure.
    """
    platform_id = f"meta_{int(time.time())}"
    log.info("[STUB] Pushed creative %s to Meta Ads → %s", creative.get("id"), platform_id)
    return {
        "success": True,
        "platform": "META",
        "platform_id": platform_id,
        "message": f"Ad created in adset for {creative.get('campaign_name', 'unknown')}",
    }


def push_to_microsoft(creative: dict, config: dict = None) -> dict:
    """Push a creative to Microsoft (Bing) Ads.

    In production this would use the Bing Ads SOAP API via the
    bingads Python SDK:

        from bingads.v13.bulk import BulkServiceManager
        from bingads.v13.campaignmanagement import ResponsiveSearchAd

        ad = ResponsiveSearchAd()
        ad.Headlines = [{"Text": h} for h in creative["headlines"]]
        ad.Descriptions = [{"Text": d} for d in creative["descriptions"]]
        ad.FinalUrls = {"string": [creative["final_url"]]}
        ad.Path1 = creative.get("display_path", [""])[0]
        ad.Path2 = creative.get("display_path", ["", ""])[1]

        campaign_service.add_ads(
            AdGroupId=config["ad_group_id"], Ads={"Ad": [ad]}
        )

    Returns a result dict indicating success or failure.
    """
    platform_id = f"msads_{int(time.time())}"
    log.info("[STUB] Pushed creative %s to Microsoft Ads → %s", creative.get("id"), platform_id)
    return {
        "success": True,
        "platform": "MICROSOFT",
        "platform_id": platform_id,
        "message": f"Ad created in campaign {creative.get('campaign_id', 'unknown')}",
    }


def push_to_tiktok(creative: dict, config: dict = None) -> dict:
    """Push a creative to TikTok Ads.

    In production this would call the TikTok Marketing API:

        POST https://business-api.tiktok.com/open_api/v1.3/ad/create/
        Headers: {"Access-Token": config["access_token"]}
        Body: {
            "advertiser_id": config["advertiser_id"],
            "adgroup_id": config["adgroup_id"],
            "ad_name": creative["campaign_name"],
            "ad_text": creative["descriptions"][0][:100],
            "call_to_action": creative["cta"].upper().replace(" ", "_"),
            "landing_page_url": creative["final_url"],
            "video_id": creative.get("video_url"),
        }

    Returns a result dict indicating success or failure.
    """
    platform_id = f"tt_{int(time.time())}"
    log.info("[STUB] Pushed creative %s to TikTok Ads → %s", creative.get("id"), platform_id)
    return {
        "success": True,
        "platform": "TIKTOK",
        "platform_id": platform_id,
        "message": f"Ad created for {creative.get('campaign_name', 'unknown')}",
    }


_PUSH_DISPATCH = {
    "GOOGLE": push_to_google,
    "META": push_to_meta,
    "MICROSOFT": push_to_microsoft,
    "TIKTOK": push_to_tiktok,
}


def push_creative(creative_id: str) -> dict:
    """Push an approved creative to its ad platform.

    Dispatches to the correct platform handler, updates status to 'live',
    records timestamps, and appends to the push log.
    """
    try:
        data = load_creatives()
        creative = None
        for c in data["creatives"]:
            if c["id"] == creative_id:
                creative = c
                break

        if not creative:
            return {"success": False, "message": f"Creative {creative_id} not found"}

        if creative["status"] != "approved":
            return {
                "success": False,
                "message": f"Creative must be approved before pushing (current: {creative['status']})",
            }

        platform = creative.get("platform", "").upper()
        handler = _PUSH_DISPATCH.get(platform)
        if not handler:
            return {"success": False, "message": f"Unsupported platform: {platform}"}

        result = handler(creative)

        if result.get("success"):
            creative["status"] = "live"
            creative["pushed_at"] = _now()
            creative["modified"] = _now()
            data.setdefault("push_log", []).append({
                "timestamp": _now(),
                "creative_id": creative_id,
                "platform": platform,
                "action": "create",
                "status": "success",
                "details": result.get("message", ""),
            })
        else:
            data.setdefault("push_log", []).append({
                "timestamp": _now(),
                "creative_id": creative_id,
                "platform": platform,
                "action": "create",
                "status": "failed",
                "details": result.get("message", ""),
            })

        save_creatives(data)
        log.info("Push result for %s: %s", creative_id, result)
        return result

    except Exception:
        log.exception("Failed to push creative %s", creative_id)
        return {"success": False, "message": "Internal error during push"}


# ---------------------------------------------------------------------------
# Analytics / Reporting
# ---------------------------------------------------------------------------

def get_push_log(client_name: str = None, limit: int = 50) -> list:
    """Return recent push activity, optionally filtered by client."""
    data = load_creatives()
    entries = data.get("push_log", [])

    if client_name:
        creative_ids = {
            c["id"] for c in data.get("creatives", [])
            if c.get("client_name") == client_name
        }
        entries = [e for e in entries if e.get("creative_id") in creative_ids]

    return entries[-limit:]


def get_creative_stats() -> dict:
    """Return aggregate counts by status, platform, and client."""
    data = load_creatives()
    creatives = data.get("creatives", [])

    by_status: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    by_client: dict[str, int] = {}

    for c in creatives:
        s = c.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

        p = c.get("platform", "unknown")
        by_platform[p] = by_platform.get(p, 0) + 1

        cl = c.get("client_name", "unknown")
        by_client[cl] = by_client.get(cl, 0) + 1

    return {
        "total": len(creatives),
        "by_status": by_status,
        "by_platform": by_platform,
        "by_client": by_client,
        "push_log_entries": len(data.get("push_log", [])),
    }


def get_version_diff(creative_id: str, v1: int, v2: int) -> dict:
    """Compare two versions of a creative, returning field-level diffs."""
    creative = get_creative(creative_id)
    if not creative:
        return {"error": f"Creative {creative_id} not found"}

    versions = {v["version"]: v for v in creative.get("versions", [])}
    ver1 = versions.get(v1)
    ver2 = versions.get(v2)

    if not ver1 or not ver2:
        missing = []
        if not ver1:
            missing.append(str(v1))
        if not ver2:
            missing.append(str(v2))
        return {"error": f"Version(s) {', '.join(missing)} not found"}

    diff: dict = {"creative_id": creative_id, "v1": v1, "v2": v2, "changes": {}}

    h1 = set(ver1.get("headlines", []))
    h2 = set(ver2.get("headlines", []))
    if h1 != h2:
        diff["changes"]["headlines"] = {
            "added": sorted(h2 - h1),
            "removed": sorted(h1 - h2),
        }

    d1 = set(ver1.get("descriptions", []))
    d2 = set(ver2.get("descriptions", []))
    if d1 != d2:
        diff["changes"]["descriptions"] = {
            "added": sorted(d2 - d1),
            "removed": sorted(d1 - d2),
        }

    if not diff["changes"]:
        diff["changes"] = "No differences"

    return diff


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------

def seed_demo_creatives() -> None:
    """Create realistic demo creatives across platforms and statuses."""
    now = "2026-04-02T12:00:00"

    def _mk_versions(headlines, descriptions, extra=None):
        vlist = [{
            "version": 1,
            "timestamp": now,
            "headlines": list(headlines),
            "descriptions": list(descriptions),
            "change_note": "Initial draft",
        }]
        if extra:
            for v in extra:
                vlist.append(v)
        return vlist

    creatives = [
        # 1 — Google RSA, Solara Beauty, LIVE
        {
            "id": "cr_demo_001",
            "client_name": "Solara Beauty",
            "campaign_id": "C-10034",
            "campaign_name": "Solara | Brand | Search",
            "platform": "GOOGLE",
            "ad_type": "responsive_search",
            "status": "live",
            "headlines": [
                "Shop Solara Beauty Today",
                "Premium Skincare Products",
                "Get 20% Off First Order",
                "Award-Winning Skincare",
                "Free Shipping Over $50",
            ],
            "descriptions": [
                "Discover our award-winning skincare line. Free shipping on orders over $50.",
                "Natural ingredients, proven results. Join 50,000+ happy customers.",
            ],
            "final_url": "https://solarabeauty.com",
            "display_path": ["shop", "skincare"],
            "image_url": None,
            "video_url": None,
            "cta": "Shop Now",
            "created": now,
            "modified": "2026-04-02T16:00:00",
            "approved_at": "2026-04-02T15:00:00",
            "pushed_at": "2026-04-02T16:00:00",
            "approved_by": "kalina",
            "version": 2,
            "versions": _mk_versions(
                ["Shop Solara Beauty", "Skincare Products", "20% Off"],
                ["Discover our skincare line."],
                [{
                    "version": 2,
                    "timestamp": "2026-04-02T14:00:00",
                    "headlines": [
                        "Shop Solara Beauty Today",
                        "Premium Skincare Products",
                        "Get 20% Off First Order",
                        "Award-Winning Skincare",
                        "Free Shipping Over $50",
                    ],
                    "descriptions": [
                        "Discover our award-winning skincare line. Free shipping on orders over $50.",
                        "Natural ingredients, proven results. Join 50,000+ happy customers.",
                    ],
                    "change_note": "Expanded headlines and descriptions",
                }],
            ),
            "ai_generated": True,
            "generation_prompt": "Write Google responsive search ad for luxury skincare brand",
            "performance": {
                "impressions": 12400,
                "clicks": 312,
                "ctr": 2.52,
                "conversions": 28,
                "cost": 187.50,
            },
            "tags": ["brand", "search"],
        },

        # 2 — Google RSA, Solara Beauty, DRAFT (new variation)
        {
            "id": "cr_demo_002",
            "client_name": "Solara Beauty",
            "campaign_id": "C-10034",
            "campaign_name": "Solara | Brand | Search",
            "platform": "GOOGLE",
            "ad_type": "responsive_search",
            "status": "draft",
            "headlines": [
                "Solara Beauty — Official",
                "Luxury Skincare Made Simple",
                "Try Our Bestsellers",
                "Clean Beauty, Real Results",
            ],
            "descriptions": [
                "From serums to moisturizers, Solara has everything your skin craves.",
                "Ethically sourced, dermatologist approved. Shop the full collection.",
            ],
            "final_url": "https://solarabeauty.com/bestsellers",
            "display_path": ["shop", "bestsellers"],
            "image_url": None,
            "video_url": None,
            "cta": "Shop Now",
            "created": "2026-04-02T17:00:00",
            "modified": "2026-04-02T17:00:00",
            "approved_at": None,
            "pushed_at": None,
            "approved_by": None,
            "version": 1,
            "versions": _mk_versions(
                [
                    "Solara Beauty — Official",
                    "Luxury Skincare Made Simple",
                    "Try Our Bestsellers",
                    "Clean Beauty, Real Results",
                ],
                [
                    "From serums to moisturizers, Solara has everything your skin craves.",
                    "Ethically sourced, dermatologist approved. Shop the full collection.",
                ],
            ),
            "ai_generated": True,
            "generation_prompt": "Generate variation of existing Solara RSA with focus on bestsellers",
            "performance": None,
            "tags": ["brand", "search", "variation"],
        },

        # 3 — Meta social ad, TrueForm Athletics, APPROVED
        {
            "id": "cr_demo_003",
            "client_name": "TrueForm Athletics",
            "campaign_id": "C-20071",
            "campaign_name": "TrueForm | Summer Drop | Social",
            "platform": "META",
            "ad_type": "social_post",
            "status": "approved",
            "headlines": [
                "Your new gym partner just landed",
            ],
            "descriptions": [
                "The Summer '26 collection is here. Breathable fabrics, bold colors, "
                "and fits that move with you. Tap to shop.",
            ],
            "final_url": "https://trueformathletics.com/summer26",
            "display_path": None,
            "image_url": "https://cdn.trueform.demo/summer26_hero.jpg",
            "video_url": None,
            "cta": "Shop Now",
            "created": "2026-04-01T10:00:00",
            "modified": "2026-04-02T09:00:00",
            "approved_at": "2026-04-02T09:00:00",
            "pushed_at": None,
            "approved_by": "kalina",
            "version": 2,
            "versions": _mk_versions(
                ["Summer collection is live"],
                ["New athletic wear for your best season yet. Shop now."],
                [{
                    "version": 2,
                    "timestamp": "2026-04-02T08:00:00",
                    "headlines": ["Your new gym partner just landed"],
                    "descriptions": [
                        "The Summer '26 collection is here. Breathable fabrics, bold colors, "
                        "and fits that move with you. Tap to shop.",
                    ],
                    "change_note": "Refined copy for engagement",
                }],
            ),
            "ai_generated": False,
            "generation_prompt": None,
            "performance": None,
            "tags": ["social", "summer", "product-launch"],
        },

        # 4 — Meta social ad, TrueForm Athletics, DRAFT
        {
            "id": "cr_demo_004",
            "client_name": "TrueForm Athletics",
            "campaign_id": "C-20071",
            "campaign_name": "TrueForm | Summer Drop | Retargeting",
            "platform": "META",
            "ad_type": "social_post",
            "status": "draft",
            "headlines": [
                "Still thinking about it?",
            ],
            "descriptions": [
                "That TrueForm set you were eyeing is selling fast. "
                "Come back and grab yours before it's gone.",
            ],
            "final_url": "https://trueformathletics.com/summer26",
            "display_path": None,
            "image_url": "https://cdn.trueform.demo/retarget_carousel.jpg",
            "video_url": None,
            "cta": "Shop Now",
            "created": "2026-04-02T11:00:00",
            "modified": "2026-04-02T11:00:00",
            "approved_at": None,
            "pushed_at": None,
            "approved_by": None,
            "version": 1,
            "versions": _mk_versions(
                ["Still thinking about it?"],
                [
                    "That TrueForm set you were eyeing is selling fast. "
                    "Come back and grab yours before it's gone.",
                ],
            ),
            "ai_generated": True,
            "generation_prompt": "Write retargeting ad for athletic wear brand, urgency tone",
            "performance": None,
            "tags": ["social", "retargeting"],
        },

        # 5 — Microsoft RSA, PetPals, REVIEW
        {
            "id": "cr_demo_005",
            "client_name": "PetPals",
            "campaign_id": "C-30012",
            "campaign_name": "PetPals | Generic | Search",
            "platform": "MICROSOFT",
            "ad_type": "responsive_search",
            "status": "review",
            "headlines": [
                "PetPals — Premium Pet Food",
                "Vet-Recommended Nutrition",
                "Free Delivery on First Box",
                "Healthy Pets, Happy Homes",
            ],
            "descriptions": [
                "Wholesome, vet-approved recipes delivered to your door. Try PetPals risk-free.",
                "Real meat, real vegetables, zero fillers. See why 30,000 pet parents switched.",
            ],
            "final_url": "https://petpals.demo/shop",
            "display_path": ["shop", "pet-food"],
            "image_url": None,
            "video_url": None,
            "cta": "Shop Now",
            "created": "2026-04-01T14:00:00",
            "modified": "2026-04-02T10:00:00",
            "approved_at": None,
            "pushed_at": None,
            "approved_by": None,
            "version": 1,
            "versions": _mk_versions(
                [
                    "PetPals — Premium Pet Food",
                    "Vet-Recommended Nutrition",
                    "Free Delivery on First Box",
                    "Healthy Pets, Happy Homes",
                ],
                [
                    "Wholesome, vet-approved recipes delivered to your door. Try PetPals risk-free.",
                    "Real meat, real vegetables, zero fillers. See why 30,000 pet parents switched.",
                ],
            ),
            "ai_generated": True,
            "generation_prompt": "Write Bing search ad for premium pet food subscription service",
            "performance": None,
            "tags": ["generic", "search", "pet-food"],
        },

        # 6 — TikTok ad, TrueForm Athletics, DRAFT
        {
            "id": "cr_demo_006",
            "client_name": "TrueForm Athletics",
            "campaign_id": "C-20090",
            "campaign_name": "TrueForm | TikTok | Summer Hype",
            "platform": "TIKTOK",
            "ad_type": "video_script",
            "status": "draft",
            "headlines": [
                "POV: your gym fit finally matches your energy",
            ],
            "descriptions": [
                "Summer '26 drop just hit. Breathable, bold, and built different. "
                "Link in bio.",
            ],
            "final_url": "https://trueformathletics.com/tiktok",
            "display_path": None,
            "image_url": None,
            "video_url": "https://cdn.trueform.demo/tt_summer26.mp4",
            "cta": "Shop Now",
            "created": "2026-04-02T13:00:00",
            "modified": "2026-04-02T13:00:00",
            "approved_at": None,
            "pushed_at": None,
            "approved_by": None,
            "version": 1,
            "versions": _mk_versions(
                ["POV: your gym fit finally matches your energy"],
                [
                    "Summer '26 drop just hit. Breathable, bold, and built different. "
                    "Link in bio.",
                ],
            ),
            "ai_generated": True,
            "generation_prompt": "Write TikTok-native video ad script for athletic wear, Gen-Z tone",
            "performance": None,
            "tags": ["tiktok", "video", "summer"],
        },
    ]

    push_log = [
        {
            "timestamp": "2026-04-02T16:00:00",
            "creative_id": "cr_demo_001",
            "platform": "GOOGLE",
            "action": "create",
            "status": "success",
            "details": "Ad created in campaign C-10034",
        },
    ]

    data = {"creatives": creatives, "push_log": push_log}

    try:
        CREATIVES_PATH.parent.mkdir(parents=True, exist_ok=True)
        CREATIVES_PATH.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        log.info("Seeded %d demo creatives to %s", len(creatives), CREATIVES_PATH)
    except Exception:
        log.exception("Failed to seed demo creatives")
