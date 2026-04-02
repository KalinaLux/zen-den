"""Analytics module for Zen Den — marketing automation analytics.

Budget pacing, anomaly detection, meeting prep briefs, change tracking,
time-saved metrics, and weekly recaps for Google Ads campaign management.
"""

import json
import sys
import calendar
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Data directory resolution (PyInstaller-aware)
# ---------------------------------------------------------------------------

def _data_dir():
    if getattr(sys, "_MEIPASS", None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


def _parse_budget(raw: str) -> float:
    """'$1,200.00' → 1200.0"""
    if not raw:
        return 0.0
    return float(raw.replace("$", "").replace(",", ""))


def _now():
    return datetime.now(timezone.utc)


# =========================================================================
# 1. Budget Pacing
# =========================================================================

def calculate_budget_pacing(data):
    """Return pacing info for every client and campaign.

    Skips PAUSED/REMOVED campaigns for numeric pacing but still includes
    them with ``pace_status`` set to ``"paused"`` or ``"removed"``.
    """
    now = _now()
    days_elapsed = now.day
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_remaining = days_in_month - days_elapsed

    results = []

    for client in data.get("clients", []):
        camp_results = []
        total_daily = 0.0
        total_spent = 0.0
        active_statuses = []

        for camp in client.get("campaigns", []):
            status = camp.get("status", "UNKNOWN").upper()
            daily = _parse_budget(camp.get("budget_daily", "$0"))
            perf = camp.get("performance", {})
            spent = perf.get("cost", 0.0)

            entry = {
                "name": camp.get("name", ""),
                "status": status,
                "daily_budget": daily,
                "monthly_budget": round(daily * 30, 2),
                "spent": spent,
                "days_elapsed": days_elapsed,
                "days_in_month": days_in_month,
                "days_remaining": days_remaining,
            }

            if status in ("PAUSED", "REMOVED"):
                entry.update({
                    "expected_spend": 0.0,
                    "pace_percent": 0.0,
                    "pace_status": status.lower(),
                    "projected_monthly": 0.0,
                    "budget_remaining": round(daily * 30 - spent, 2),
                })
            else:
                expected = daily * days_elapsed
                pace_pct = (spent / expected * 100) if expected else 0.0
                projected = (spent / days_elapsed * days_in_month) if days_elapsed else 0.0

                if pace_pct < 85:
                    pace_status = "underspending"
                elif pace_pct > 115:
                    pace_status = "overspending"
                else:
                    pace_status = "on_track"

                entry.update({
                    "expected_spend": round(expected, 2),
                    "pace_percent": round(pace_pct, 1),
                    "pace_status": pace_status,
                    "projected_monthly": round(projected, 2),
                    "budget_remaining": round(daily * 30 - spent, 2),
                })

                total_daily += daily
                total_spent += spent
                active_statuses.append(pace_status)

            camp_results.append(entry)

        over = active_statuses.count("overspending")
        under = active_statuses.count("underspending")
        if over > under:
            overall = "overspending"
        elif under > over:
            overall = "underspending"
        else:
            overall = "on_track"

        results.append({
            "client": client.get("name", ""),
            "campaigns": camp_results,
            "total_daily_budget": round(total_daily, 2),
            "total_spent": round(total_spent, 2),
            "overall_pace_status": overall,
        })

    return results


# =========================================================================
# 2. Performance Anomaly Detection
# =========================================================================

_RECOMMENDATIONS = {
    "roas_critical": (
        "Review keyword performance and pause low-converting terms. "
        "Consider adjusting bids or audience targeting."
    ),
    "roas_warning": (
        "Investigate top-spending keywords for efficiency. "
        "Test new ad copy and landing page variants to improve conversion value."
    ),
    "ctr_search": (
        "Test new responsive search ad variations. "
        "Review ad relevance and keyword-to-ad alignment."
    ),
    "ctr_display": (
        "Low CTR is typical for Display. Monitor view-through conversions "
        "and consider refreshing creative assets quarterly."
    ),
    "cpc_high": (
        "Review auction insights for competitor pressure. "
        "Consider shifting budget to lower-CPC ad groups or broadening match types."
    ),
    "conv_rate_low": (
        "Audit landing page experience and load speed. "
        "Check audience targeting and consider adding negative keywords."
    ),
    "zero_conversions": (
        "Pause campaign immediately and audit tracking setup. "
        "Verify conversion actions are firing and review search term report."
    ),
    "promo_disapproved": (
        "Review Google's disapproval reason in the Ads UI and resubmit "
        "with compliant copy. Consider contacting Google support if unclear."
    ),
}


def detect_anomalies(data):
    """Detect performance anomalies across all ENABLED campaigns."""
    alerts = []

    for client in data.get("clients", []):
        client_name = client.get("name", "")

        for camp in client.get("campaigns", []):
            if camp.get("status", "").upper() != "ENABLED":
                continue

            perf = camp.get("performance", {})
            network = camp.get("network", "SEARCH").upper()
            camp_name = camp.get("name", "")

            roas = perf.get("roas", 0)
            ctr = perf.get("ctr", 0)
            cpc = perf.get("avg_cpc", 0)
            conv_rate = perf.get("conv_rate", 0)
            cost = perf.get("cost", 0)
            conversions = perf.get("conversions", 0)

            # ROAS checks
            if cost > 0 and roas < 1.0:
                alerts.append({
                    "client": client_name,
                    "campaign": camp_name,
                    "metric": "roas",
                    "metric_label": "ROAS",
                    "current_value": roas,
                    "threshold": 1.0,
                    "severity": "critical",
                    "message": (
                        f"ROAS is {roas}x — below breakeven (1.0x). "
                        "Losing money on this campaign."
                    ),
                    "recommendation": _RECOMMENDATIONS["roas_critical"],
                })
            elif cost > 0 and 1.0 <= roas < 2.0:
                alerts.append({
                    "client": client_name,
                    "campaign": camp_name,
                    "metric": "roas",
                    "metric_label": "ROAS",
                    "current_value": roas,
                    "threshold": 2.0,
                    "severity": "warning",
                    "message": (
                        f"ROAS is {roas}x — above breakeven but below 2.0x target."
                    ),
                    "recommendation": _RECOMMENDATIONS["roas_warning"],
                })

            # CTR checks
            if network == "SEARCH" and ctr < 2.0 and perf.get("impressions", 0) > 0:
                alerts.append({
                    "client": client_name,
                    "campaign": camp_name,
                    "metric": "ctr",
                    "metric_label": "CTR",
                    "current_value": ctr,
                    "threshold": 2.0,
                    "severity": "warning",
                    "message": (
                        f"CTR is {ctr}% on Search — ad copy may need refresh."
                    ),
                    "recommendation": _RECOMMENDATIONS["ctr_search"],
                })
            elif network == "DISPLAY" and ctr < 0.5 and perf.get("impressions", 0) > 0:
                alerts.append({
                    "client": client_name,
                    "campaign": camp_name,
                    "metric": "ctr",
                    "metric_label": "CTR",
                    "current_value": ctr,
                    "threshold": 0.5,
                    "severity": "info",
                    "message": (
                        f"CTR is {ctr}% on Display — normal for display network."
                    ),
                    "recommendation": _RECOMMENDATIONS["ctr_display"],
                })

            # CPC check (Search only)
            if network == "SEARCH" and cpc > 5.0:
                alerts.append({
                    "client": client_name,
                    "campaign": camp_name,
                    "metric": "avg_cpc",
                    "metric_label": "Avg. CPC",
                    "current_value": cpc,
                    "threshold": 5.0,
                    "severity": "warning",
                    "message": f"CPC is ${cpc:.2f} on Search — above $5.00 threshold.",
                    "recommendation": _RECOMMENDATIONS["cpc_high"],
                })

            # Conversion rate check
            if conv_rate < 1.0 and perf.get("clicks", 0) > 0:
                alerts.append({
                    "client": client_name,
                    "campaign": camp_name,
                    "metric": "conv_rate",
                    "metric_label": "Conv. Rate",
                    "current_value": conv_rate,
                    "threshold": 1.0,
                    "severity": "warning",
                    "message": (
                        f"Conversion rate is {conv_rate}% — below 1.0% floor."
                    ),
                    "recommendation": _RECOMMENDATIONS["conv_rate_low"],
                })

            # Spending with zero conversions
            if cost > 0 and conversions == 0:
                alerts.append({
                    "client": client_name,
                    "campaign": camp_name,
                    "metric": "conversions",
                    "metric_label": "Conversions",
                    "current_value": 0,
                    "threshold": 1,
                    "severity": "critical",
                    "message": (
                        f"Spent ${cost:,.2f} with zero conversions. "
                        "Budget is being wasted."
                    ),
                    "recommendation": _RECOMMENDATIONS["zero_conversions"],
                })

            # Disapproved promos
            for promo in camp.get("promos", []):
                if promo.get("status", "").upper() == "DISAPPROVED":
                    reason = promo.get("reason", "No reason provided")
                    alerts.append({
                        "client": client_name,
                        "campaign": camp_name,
                        "metric": "promo_status",
                        "metric_label": "Promo Status",
                        "current_value": "DISAPPROVED",
                        "threshold": "APPROVED",
                        "severity": "critical",
                        "message": (
                            f"Promo \"{promo.get('text', '')}\" disapproved by Google. "
                            f"Reason: {reason}"
                        ),
                        "recommendation": _RECOMMENDATIONS["promo_disapproved"],
                    })

    return alerts


# =========================================================================
# 3. Meeting Prep Brief
# =========================================================================

def generate_meeting_prep(client_data):
    """Generate a meeting prep brief for a single client dict.

    ``client_data`` is one element from ``data["clients"]``.
    """
    now = _now()
    campaigns = client_data.get("campaigns", [])

    enabled = [c for c in campaigns if c.get("status", "").upper() == "ENABLED"]
    paused = [c for c in campaigns if c.get("status", "").upper() == "PAUSED"]
    removed = [c for c in campaigns if c.get("status", "").upper() == "REMOVED"]

    total_spend = sum(c.get("performance", {}).get("cost", 0) for c in campaigns)
    total_conv = sum(c.get("performance", {}).get("conversions", 0) for c in campaigns)
    total_value = sum(c.get("performance", {}).get("conv_value", 0) for c in campaigns)
    avg_roas = round(total_value / total_spend, 2) if total_spend else 0.0

    # --- highlights (strong performers among enabled) ---
    highlights = []
    for c in enabled:
        p = c.get("performance", {})
        roas = p.get("roas", 0)
        conv = p.get("conversions", 0)
        conv_rate = p.get("conv_rate", 0)
        name = c.get("name", "")

        if roas >= 3.0:
            highlights.append(
                f"{name} performing strongly — ROAS {roas}x, "
                f"{conv:,} conversions"
            )
        elif roas >= 2.0:
            highlights.append(
                f"{name} performing well — ROAS {roas}x, "
                f"{conv:,} conversions"
            )
        if conv_rate >= 5.0 and roas >= 2.0:
            highlights.append(
                f"{name} showing strong conversion rate at {conv_rate}%"
            )

    # --- concerns ---
    concerns = []
    for c in enabled:
        p = c.get("performance", {})
        roas = p.get("roas", 0)
        cost = p.get("cost", 0)
        conv = p.get("conversions", 0)
        name = c.get("name", "")

        if cost > 0 and roas < 1.0:
            concerns.append(
                f"{name} — ROAS {roas}x (below breakeven). "
                f"Spent ${cost:,.2f} with only {conv} conversions."
            )
        elif cost > 0 and roas < 2.0:
            concerns.append(
                f"{name} — ROAS {roas}x, barely above breakeven."
            )
        if cost > 0 and conv == 0:
            concerns.append(
                f"{name} — spending ${cost:,.2f} with zero conversions."
            )

    for c in paused:
        p = c.get("performance", {})
        roas = p.get("roas", 0)
        name = c.get("name", "")
        start = c.get("start_date", "")

        if roas > 0 and roas < 1.0:
            concerns.append(
                f"{name} paused — ROAS was {roas}x (below breakeven)"
            )
        elif start > now.strftime("%Y-%m-%d"):
            concerns.append(
                f"{name} paused — scheduled to enable {start}"
            )

    # Check for disapproved promos
    for c in campaigns:
        for promo in c.get("promos", []):
            if promo.get("status", "").upper() == "DISAPPROVED":
                concerns.append(
                    f"Promo \"{promo.get('text', '')}\" DISAPPROVED — "
                    f"{promo.get('reason', 'needs review')}"
                )

    # --- talking points ---
    talking_points = []
    for c in enabled:
        p = c.get("performance", {})
        roas = p.get("roas", 0)
        conv_rate = p.get("conv_rate", 0)
        daily = _parse_budget(c.get("budget_daily", "$0"))
        name = c.get("name", "")

        if roas >= 2.5 and conv_rate >= 4.0:
            suggested = round(daily * 1.5, -1)
            talking_points.append(
                f"Recommend increasing {name} budget — strong performance "
                f"at {conv_rate}% conv rate"
            )
        elif roas < 1.5 and p.get("cost", 0) > 0:
            talking_points.append(
                f"{name} needs strategy review before scaling further"
            )

    for c in paused:
        name = c.get("name", "")
        start = c.get("start_date", "")
        daily = _parse_budget(c.get("budget_daily", "$0"))
        promos = c.get("promos", [])
        approved_promos = [pr for pr in promos if pr.get("status", "").upper() == "APPROVED"]

        if start > now.strftime("%Y-%m-%d") and approved_promos:
            talking_points.append(
                f"{name} ready to launch — promo approved, "
                f"budget set at ${daily:,.0f}/day"
            )
        elif start > now.strftime("%Y-%m-%d"):
            talking_points.append(
                f"{name} scheduled for {start} — confirm creative assets"
            )

    # --- promos status ---
    promos_status = []
    for c in campaigns:
        for promo in c.get("promos", []):
            entry = {
                "text": promo.get("text", ""),
                "status": promo.get("status", "UNKNOWN"),
                "serving": promo.get("serving", False),
            }
            if promo.get("reason"):
                entry["note"] = promo["reason"]
            elif not promo.get("serving") and c.get("status", "").upper() == "PAUSED":
                entry["note"] = (
                    f"Campaign paused"
                    + (f", scheduled {c.get('start_date', '')}"
                       if c.get("start_date", "") > now.strftime("%Y-%m-%d")
                       else "")
                )
            promos_status.append(entry)

    # --- action items ---
    action_items = []
    for c in enabled:
        p = c.get("performance", {})
        roas = p.get("roas", 0)
        conv_rate = p.get("conv_rate", 0)
        daily = _parse_budget(c.get("budget_daily", "$0"))
        name = c.get("name", "")

        if roas >= 2.5 and conv_rate >= 4.0:
            suggested = int(round(daily * 1.5, -1))
            action_items.append(
                f"Get client approval to increase {name} daily budget to ${suggested:,}"
            )
        elif roas < 1.5 and p.get("cost", 0) > 0:
            action_items.append(
                f"Prepare {name} recovery plan with new keyword list"
            )

    for c in paused:
        start = c.get("start_date", "")
        name = c.get("name", "")
        if start > now.strftime("%Y-%m-%d"):
            action_items.append(
                f"Confirm {name} creative assets are ready"
            )

    for c in campaigns:
        for promo in c.get("promos", []):
            if promo.get("status", "").upper() == "DISAPPROVED":
                action_items.append(
                    f"Resolve disapproved promo: \"{promo.get('text', '')}\""
                )

    summary_parts = [
        f"{len(campaigns)} campaigns",
        f"({len(enabled)} enabled"
        + (f", {len(paused)} paused" if paused else "")
        + (f", {len(removed)} removed" if removed else "")
        + ")",
    ]
    summary = (
        f"{' '.join(summary_parts)}. "
        f"Total spend ${total_spend:,.2f}. Overall ROAS: {avg_roas}x."
    )

    return {
        "client": client_data.get("name", ""),
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "highlights": highlights,
        "concerns": concerns,
        "talking_points": talking_points,
        "key_metrics": {
            "total_spend": round(total_spend, 2),
            "total_conversions": total_conv,
            "avg_roas": avg_roas,
            "active_campaigns": len(enabled),
            "total_campaigns": len(campaigns),
        },
        "promos_status": promos_status,
        "action_items": action_items,
    }


# =========================================================================
# 4. Change Log Tracker
# =========================================================================

def _snapshot_dir(data_dir=None):
    d = (data_dir or _data_dir()) / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_snapshot(data, data_dir=None):
    """Save current data as a timestamped JSON snapshot."""
    snap_dir = _snapshot_dir(data_dir)
    ts = _now().strftime("%Y-%m-%dT%H:%M:%S")
    path = snap_dir / f"snapshot_{ts}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(path)


def load_latest_snapshot(data_dir=None):
    """Load the most recent snapshot, or ``None`` if none exist."""
    snap_dir = _snapshot_dir(data_dir)
    files = sorted(snap_dir.glob("snapshot_*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def track_changes(current_data, previous_data):
    """Compare current campaign data to a previous snapshot.

    Returns a list of change dicts describing every detected difference:
    status changes, budget changes, new/removed campaigns, promo status
    changes.
    """
    if previous_data is None:
        return []

    ts = _now().isoformat().replace("+00:00", "Z")
    changes = []

    prev_camps = {}
    for client in previous_data.get("clients", []):
        for camp in client.get("campaigns", []):
            prev_camps[camp["id"]] = {**camp, "_client": client.get("name", "")}

    curr_camps = {}
    for client in current_data.get("clients", []):
        for camp in client.get("campaigns", []):
            curr_camps[camp["id"]] = {**camp, "_client": client.get("name", "")}

    # New campaigns
    for cid, camp in curr_camps.items():
        if cid not in prev_camps:
            changes.append({
                "timestamp": ts,
                "client": camp["_client"],
                "campaign": camp.get("name", ""),
                "change_type": "new_campaign",
                "from": None,
                "to": camp.get("status", ""),
                "description": f"New campaign added: {camp.get('name', '')}",
            })

    # Removed campaigns
    for cid, camp in prev_camps.items():
        if cid not in curr_camps:
            changes.append({
                "timestamp": ts,
                "client": camp["_client"],
                "campaign": camp.get("name", ""),
                "change_type": "removed_campaign",
                "from": camp.get("status", ""),
                "to": None,
                "description": f"Campaign removed: {camp.get('name', '')}",
            })

    # Changes within existing campaigns
    for cid in curr_camps:
        if cid not in prev_camps:
            continue
        curr = curr_camps[cid]
        prev = prev_camps[cid]

        # Status change
        if curr.get("status") != prev.get("status"):
            changes.append({
                "timestamp": ts,
                "client": curr["_client"],
                "campaign": curr.get("name", ""),
                "change_type": "status_change",
                "from": prev.get("status"),
                "to": curr.get("status"),
                "description": f"Campaign was {curr.get('status', '').lower()}",
            })

        # Budget change
        curr_budget = _parse_budget(curr.get("budget_daily", "$0"))
        prev_budget = _parse_budget(prev.get("budget_daily", "$0"))
        if curr_budget != prev_budget:
            changes.append({
                "timestamp": ts,
                "client": curr["_client"],
                "campaign": curr.get("name", ""),
                "change_type": "budget_change",
                "from": f"${prev_budget:,.2f}",
                "to": f"${curr_budget:,.2f}",
                "description": (
                    f"Daily budget changed from ${prev_budget:,.2f} "
                    f"to ${curr_budget:,.2f}"
                ),
            })

        # Promo status changes
        prev_promos = {p.get("text", ""): p for p in prev.get("promos", [])}
        for promo in curr.get("promos", []):
            text = promo.get("text", "")
            if text in prev_promos:
                old_status = prev_promos[text].get("status", "")
                new_status = promo.get("status", "")
                if old_status != new_status:
                    changes.append({
                        "timestamp": ts,
                        "client": curr["_client"],
                        "campaign": curr.get("name", ""),
                        "change_type": "promo_status_change",
                        "from": old_status,
                        "to": new_status,
                        "description": (
                            f"Promo \"{text}\" status changed "
                            f"from {old_status} to {new_status}"
                        ),
                    })
            else:
                changes.append({
                    "timestamp": ts,
                    "client": curr["_client"],
                    "campaign": curr.get("name", ""),
                    "change_type": "new_promo",
                    "from": None,
                    "to": promo.get("status", ""),
                    "description": f"New promo added: \"{text}\"",
                })

    return changes


def get_change_log(data_dir=None, days=7):
    """Return all changes detected across snapshots within the last *days*."""
    snap_dir = _snapshot_dir(data_dir)
    files = sorted(snap_dir.glob("snapshot_*.json"))
    if len(files) < 2:
        return []

    cutoff = _now() - timedelta(days=days)
    all_changes = []

    for i in range(1, len(files)):
        # Parse timestamp from filename: snapshot_YYYY-MM-DDTHH:MM:SS.json
        stem = files[i].stem.replace("snapshot_", "")
        try:
            snap_time = datetime.fromisoformat(stem).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if snap_time < cutoff:
            continue

        prev = json.loads(files[i - 1].read_text(encoding="utf-8"))
        curr = json.loads(files[i].read_text(encoding="utf-8"))
        all_changes.extend(track_changes(curr, prev))

    return all_changes


# =========================================================================
# 5. Time-Saved Tracker
# =========================================================================

_TIME_ESTIMATES = {
    "slack_auto_reply": 3,
    "email_auto_draft": 5,
    "email_auto_send": 5,
    "report_generated": 10,
    "report_emailed": 2,
    "faq_answered": 1.5,
    "campaign_check": 1.5,
    "meeting_prep": 15,
}


def _time_stats_path(data_dir=None):
    return (data_dir or _data_dir()) / "time_stats.json"


def load_time_stats(data_dir=None):
    """Load time-saved statistics from disk.

    Returns the full stats dict, or an empty-seed structure if the file
    doesn't exist yet.
    """
    path = _time_stats_path(data_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"actions": []}


def _save_time_stats(stats, data_dir=None):
    path = _time_stats_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def record_action(data_dir=None, action_type="campaign_check", details=None):
    """Record an action that saved time.

    Valid ``action_type`` values: slack_auto_reply, email_auto_draft,
    email_auto_send, report_generated, report_emailed, faq_answered,
    campaign_check, meeting_prep.
    """
    if action_type not in _TIME_ESTIMATES:
        raise ValueError(
            f"Unknown action_type '{action_type}'. "
            f"Valid types: {', '.join(sorted(_TIME_ESTIMATES))}"
        )

    stats = load_time_stats(data_dir)
    entry = {
        "timestamp": _now().isoformat().replace("+00:00", "Z"),
        "action_type": action_type,
        "minutes_saved": _TIME_ESTIMATES[action_type],
    }
    if details:
        entry["details"] = details

    stats.setdefault("actions", []).append(entry)
    _save_time_stats(stats, data_dir)
    return entry


def get_time_summary(data_dir=None):
    """Build an aggregate summary of all recorded time-saving actions."""
    stats = load_time_stats(data_dir)
    actions = stats.get("actions", [])
    now = _now()
    today_str = now.strftime("%Y-%m-%d")
    week_ago = now - timedelta(days=7)

    breakdown = {}
    today_count = 0
    today_minutes = 0.0
    week_count = 0
    week_minutes = 0.0

    for a in actions:
        atype = a.get("action_type", "unknown")
        mins = a.get("minutes_saved", 0)

        bucket = breakdown.setdefault(atype, {"count": 0, "minutes_saved": 0.0})
        bucket["count"] += 1
        bucket["minutes_saved"] += mins

        ts_str = a.get("timestamp", "")
        if ts_str.startswith(today_str):
            today_count += 1
            today_minutes += mins
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts >= week_ago:
                week_count += 1
                week_minutes += mins
        except (ValueError, TypeError):
            pass

    for atype, bucket in breakdown.items():
        est = _TIME_ESTIMATES.get(atype, 0)
        bucket["avg_minutes"] = est

    total_actions = len(actions)
    total_minutes = sum(a.get("minutes_saved", 0) for a in actions)

    # Streak: consecutive days with at least one action, ending today
    dates_seen = set()
    for a in actions:
        ts_str = a.get("timestamp", "")[:10]
        if ts_str:
            dates_seen.add(ts_str)

    streak = 0
    check = now.date()
    while check.isoformat() in dates_seen:
        streak += 1
        check -= timedelta(days=1)

    return {
        "total_actions": total_actions,
        "estimated_minutes_saved": round(total_minutes, 1),
        "estimated_hours_saved": round(total_minutes / 60, 1),
        "breakdown": breakdown,
        "today": {
            "actions": today_count,
            "minutes_saved": round(today_minutes, 1),
        },
        "this_week": {
            "actions": week_count,
            "minutes_saved": round(week_minutes, 1),
        },
        "streak_days": streak,
    }


# =========================================================================
# 6. Weekly Recap Generator
# =========================================================================

def generate_weekly_recap(data, time_stats=None):
    """Generate a cross-client weekly recap.

    If ``time_stats`` (output of ``get_time_summary()``) is provided, the
    recap includes time-saved data.
    """
    now = _now()
    week_start = (now - timedelta(days=6)).strftime("%B %d").lstrip("0")
    week_end = now.strftime("%B %d, %Y").lstrip("0")
    week_label = f"{week_start} — {week_end}"

    clients_data = data.get("clients", [])
    total_campaigns = 0
    total_enabled = 0
    total_paused = 0
    total_removed = 0

    client_sections = []
    all_wins = []
    all_attention = []

    for client in clients_data:
        client_name = client.get("name", "")
        campaigns = client.get("campaigns", [])
        total_campaigns += len(campaigns)

        enabled = [c for c in campaigns if c.get("status", "").upper() == "ENABLED"]
        paused_list = [c for c in campaigns if c.get("status", "").upper() == "PAUSED"]
        removed_list = [c for c in campaigns if c.get("status", "").upper() == "REMOVED"]
        total_enabled += len(enabled)
        total_paused += len(paused_list)
        total_removed += len(removed_list)

        spend = sum(c.get("performance", {}).get("cost", 0) for c in campaigns)
        convs = sum(c.get("performance", {}).get("conversions", 0) for c in campaigns)
        value = sum(c.get("performance", {}).get("conv_value", 0) for c in campaigns)
        roas = round(value / spend, 2) if spend else 0.0

        highlights = []
        client_concerns = []

        for c in enabled:
            p = c.get("performance", {})
            c_roas = p.get("roas", 0)
            c_conv = p.get("conversions", 0)
            c_conv_rate = p.get("conv_rate", 0)
            c_cost = p.get("cost", 0)
            name = c.get("name", "")

            if c_roas >= 3.0:
                msg = f"{name} strong at {c_roas}x ROAS"
                highlights.append(msg)
                all_wins.append(f"{client_name}: {msg}")
            elif c_roas >= 2.0:
                highlights.append(f"{name} solid at {c_roas}x ROAS")

            if c_conv_rate >= 5.0:
                win = f"{name} converting at {c_conv_rate}%"
                all_wins.append(f"{client_name}: {win}")

            if c_cost > 0 and c_roas < 1.0:
                concern = f"{name} ROAS at {c_roas}x — below breakeven"
                client_concerns.append(concern)
                all_attention.append(f"{client_name}: {concern}")
            elif c_cost > 0 and c_roas < 1.5:
                concern = f"{name} ROAS at {c_roas}x — barely breaking even"
                client_concerns.append(concern)
                all_attention.append(f"{client_name}: {concern}")

            if c_cost > 0 and c_conv == 0:
                concern = f"{name} spending with zero conversions"
                client_concerns.append(concern)
                all_attention.append(f"{client_name}: {concern}")

            for promo in c.get("promos", []):
                if promo.get("status", "").upper() == "DISAPPROVED":
                    concern = (
                        f"{name} promo DISAPPROVED — action needed"
                    )
                    client_concerns.append(concern)
                    all_attention.append(f"{client_name}: {concern}")

        client_sections.append({
            "name": client_name,
            "highlights": highlights,
            "concerns": client_concerns,
            "spend": round(spend, 2),
            "conversions": convs,
            "roas": roas,
        })

    summary = (
        f"Managing {len(clients_data)} clients, {total_campaigns} campaigns. "
        f"{total_enabled} active"
        + (f", {total_paused} paused" if total_paused else "")
        + (f", {total_removed} removed" if total_removed else "")
        + "."
    )

    result = {
        "week_of": week_label,
        "summary": summary,
        "clients": client_sections,
        "top_wins": all_wins[:5],
        "needs_attention": all_attention[:5],
    }

    if time_stats:
        result["time_saved"] = {
            "hours": time_stats.get("estimated_hours_saved", 0),
            "actions": time_stats.get("total_actions", 0),
        }

    return result
