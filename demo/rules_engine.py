"""Zen Den — Visual Automation Rules Engine

A rule-based automation system where users create IF/THEN rules through the
UI.  Rules are stored as JSON and evaluated at runtime against incoming emails
and Slack messages.

Usage:
    from rules_engine import process_message, create_rule, get_rule_templates
"""

import json
import logging
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("zen.rules")

# ---------------------------------------------------------------------------
# Data directory resolution (PyInstaller-aware)
# ---------------------------------------------------------------------------

def _data_dir():
    if getattr(sys, "_MEIPASS", None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


RULES_PATH = _data_dir() / "automation_rules.json"

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_rules() -> list:
    """Load rules from JSON file; return empty list if missing or corrupt."""
    try:
        if RULES_PATH.exists():
            return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.exception("Failed to load rules from %s", RULES_PATH)
    return []


def save_rules(rules: list) -> None:
    """Persist the full rules list to disk."""
    try:
        RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        RULES_PATH.write_text(
            json.dumps(rules, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        log.exception("Failed to save rules to %s", RULES_PATH)


def get_rule(rule_id: str) -> dict | None:
    """Find a single rule by ID."""
    for r in load_rules():
        if r.get("id") == rule_id:
            return r
    return None


def create_rule(rule: dict) -> dict:
    """Add a new rule with an auto-generated ID and timestamp, then save."""
    rules = load_rules()
    rule["id"] = f"rule_{int(time.time())}"
    rule.setdefault("enabled", True)
    rule.setdefault("created", datetime.now(timezone.utc).isoformat())
    rule.setdefault("priority", 50)
    rule.setdefault("run_count", 0)
    rule.setdefault("last_triggered", None)
    rule.setdefault("condition_logic", "all")
    rules.append(rule)
    save_rules(rules)
    return rule


def update_rule(rule_id: str, updates: dict) -> dict | None:
    """Apply *updates* to the rule with *rule_id*. Return the updated rule."""
    rules = load_rules()
    for r in rules:
        if r.get("id") == rule_id:
            r.update(updates)
            save_rules(rules)
            return r
    return None


def delete_rule(rule_id: str) -> bool:
    """Remove a rule by ID. Return True if something was deleted."""
    rules = load_rules()
    filtered = [r for r in rules if r.get("id") != rule_id]
    if len(filtered) == len(rules):
        return False
    save_rules(filtered)
    return True


def toggle_rule(rule_id: str) -> dict | None:
    """Flip the *enabled* flag on a rule and return it."""
    rules = load_rules()
    for r in rules:
        if r.get("id") == rule_id:
            r["enabled"] = not r.get("enabled", True)
            save_rules(rules)
            return r
    return None


# ---------------------------------------------------------------------------
# Template formatting
# ---------------------------------------------------------------------------

def format_template(template: str, context: dict) -> str:
    """Interpolate *context* into *template*.

    Missing keys are left as ``{key_name}`` rather than raising.
    """
    safe = defaultdict(lambda: "", context)
    # Also offer a short body preview
    body = str(context.get("body", ""))
    safe.setdefault("body_preview", body[:120] + ("…" if len(body) > 120 else ""))
    try:
        return template.format_map(safe)
    except Exception:
        log.debug("Template formatting fell back to raw string")
        return template


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

_OPS = {}

def _register(name):
    def _dec(fn):
        _OPS[name] = fn
        return fn
    return _dec

@_register("contains")
def _op_contains(field_val, cond_val):
    return cond_val.lower() in str(field_val).lower()

@_register("not_contains")
def _op_not_contains(field_val, cond_val):
    return cond_val.lower() not in str(field_val).lower()

@_register("equals")
def _op_equals(field_val, cond_val):
    return str(field_val).lower() == str(cond_val).lower()

@_register("starts_with")
def _op_starts_with(field_val, cond_val):
    return str(field_val).lower().startswith(cond_val.lower())

@_register("ends_with")
def _op_ends_with(field_val, cond_val):
    return str(field_val).lower().endswith(cond_val.lower())

@_register("matches_regex")
def _op_matches_regex(field_val, cond_val):
    try:
        return bool(re.search(cond_val, str(field_val), re.IGNORECASE))
    except re.error:
        log.warning("Invalid regex in rule condition: %s", cond_val)
        return False

@_register("is_empty")
def _op_is_empty(field_val, _cond_val):
    return not str(field_val).strip()

@_register("is_not_empty")
def _op_is_not_empty(field_val, _cond_val):
    return bool(str(field_val).strip())

@_register("greater_than")
def _op_greater_than(field_val, cond_val):
    try:
        return float(field_val) > float(cond_val)
    except (ValueError, TypeError):
        return False

@_register("less_than")
def _op_less_than(field_val, cond_val):
    try:
        return float(field_val) < float(cond_val)
    except (ValueError, TypeError):
        return False


def evaluate_conditions(conditions: list, logic: str, context: dict) -> bool:
    """Return True if *conditions* are satisfied given *context*.

    *logic* is ``"all"`` (every condition must pass) or ``"any"`` (at least
    one must pass).
    """
    if not conditions:
        return True

    results = []
    for cond in conditions:
        field = cond.get("field", "")
        op = cond.get("op", "")
        value = cond.get("value", "")
        field_val = context.get(field, "")
        handler = _OPS.get(op)
        if handler is None:
            log.warning("Unknown operator '%s' — condition skipped", op)
            results.append(False)
            continue
        try:
            results.append(handler(field_val, value))
        except Exception:
            log.exception("Error evaluating condition %s", cond)
            results.append(False)

    if logic == "any":
        return any(results)
    return all(results)


# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------

def execute_actions(actions: list, context: dict) -> list[str]:
    """Run each action against *context* and return a list of log messages."""
    logs: list[str] = []
    for action in actions:
        atype = action.get("type", "")
        try:
            if atype == "auto_reply":
                body = format_template(action.get("template", ""), context)
                logs.append(f"Auto-reply drafted → {context.get('sender', 'unknown')}")
                context["_auto_reply"] = body

            elif atype == "forward":
                fwd_to = action.get("to", action.get("forward_to", ""))
                body = format_template(
                    action.get("template", action.get("message", "")), context
                )
                logs.append(f"Forwarded to {fwd_to}")
                context["_forward"] = {"forward_to": fwd_to, "message": body}

            elif atype == "escalate":
                logs.append("Escalated — marked as high priority")
                context["_escalated"] = True

            elif atype == "tag":
                tag = action.get("value", "untagged")
                context.setdefault("_tags", []).append(tag)
                logs.append(f"Tagged [{tag}]")

            elif atype == "log":
                msg = format_template(action.get("value", ""), context)
                logs.append(f"Log: {msg}")

            elif atype == "snooze":
                minutes = int(action.get("minutes", action.get("value", 60)))
                logs.append(f"Snoozed for {minutes} min")
                context["_snooze_minutes"] = minutes

            elif atype == "skip":
                logs.append("Marked as handled — no reply")
                context["_skipped"] = True

            elif atype == "run_script":
                script_id = action.get("script_id", action.get("value", ""))
                logs.append(f"Queued script [{script_id}]")
                context["_run_script"] = script_id

            else:
                logs.append(f"Unknown action type '{atype}' — skipped")
        except Exception:
            log.exception("Error executing action %s", action)
            logs.append(f"Error executing action '{atype}'")
    return logs


# ---------------------------------------------------------------------------
# Message processing pipeline
# ---------------------------------------------------------------------------

def process_message(context: dict) -> list[dict]:
    """Evaluate every enabled rule against *context*, execute matching rules.

    Returns an audit-friendly list of dicts:
        [{"rule_id": ..., "rule_name": ..., "actions_taken": [...]}, ...]
    """
    rules = load_rules()
    enabled = [r for r in rules if r.get("enabled", True)]
    enabled.sort(key=lambda r: r.get("priority", 50))

    results: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for rule in enabled:
        conditions = rule.get("conditions", [])
        logic = rule.get("condition_logic", "all")
        if not evaluate_conditions(conditions, logic, context):
            continue

        action_logs = execute_actions(rule.get("actions", []), context)
        rule["run_count"] = rule.get("run_count", 0) + 1
        rule["last_triggered"] = now
        results.append({
            "rule_id": rule["id"],
            "rule_name": rule.get("name", ""),
            "actions_taken": action_logs,
        })

    if results:
        save_rules(rules)

    return results


# ---------------------------------------------------------------------------
# Pre-built rule templates
# ---------------------------------------------------------------------------

def get_rule_templates() -> list[dict]:
    """Return ready-to-install rule templates for the template gallery."""
    return [
        {
            "id": "tmpl_vip_escalate",
            "name": "VIP emails → escalate",
            "description": "Escalate emails from VIP senders so they never slip through the cracks.",
            "trigger": "email",
            "conditions": [
                {"field": "sender", "op": "matches_regex",
                 "value": r"(ceo|cfo|vp|director)@"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "escalate"},
                {"type": "tag", "value": "vip"},
                {"type": "log", "value": "VIP email from {sender} escalated"},
            ],
        },
        {
            "id": "tmpl_budget_auto_reply",
            "name": "Budget questions → auto-reply",
            "description": "Auto-reply to emails asking about budgets with the latest numbers.",
            "trigger": "email",
            "conditions": [
                {"field": "subject", "op": "matches_regex",
                 "value": r"(?i)(budget|spend|monthly cost|ad spend)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "auto_reply",
                 "template": "Hi {sender_name},\n\nHere's the latest budget report for {client_name}. See attached PDF.\n\nBest,\nZen Den"},
                {"type": "tag", "value": "budget"},
                {"type": "log", "value": "Auto-replied to budget question from {sender}"},
            ],
        },
        {
            "id": "tmpl_campaign_status",
            "name": "Campaign status checks → auto-reply",
            "description": "Answer routine 'is my campaign running?' questions automatically.",
            "trigger": "email",
            "conditions": [
                {"field": "body", "op": "matches_regex",
                 "value": r"(?i)(campaign.*(status|running|live|paused|active)|is .* (on|off))"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "auto_reply",
                 "template": "Hi {sender_name},\n\nI've pulled the latest campaign status for {client_name}. All active campaigns are running normally. I'll flag anything that needs attention.\n\nBest,\nZen Den"},
                {"type": "tag", "value": "campaign-status"},
            ],
        },
        {
            "id": "tmpl_after_hours_snooze",
            "name": "After-hours emails → snooze",
            "description": "Snooze emails received outside 9-5 until the next business morning.",
            "trigger": "email",
            "conditions": [
                {"field": "timestamp", "op": "matches_regex",
                 "value": r"T(0[0-8]|1[7-9]|2[0-3])"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "snooze", "minutes": 720},
                {"type": "tag", "value": "after-hours"},
                {"type": "log", "value": "After-hours email from {sender} snoozed until morning"},
            ],
        },
        {
            "id": "tmpl_client_reports",
            "name": "Client reports → auto-reply with PDF",
            "description": "Respond to report requests with the latest generated report.",
            "trigger": "email",
            "conditions": [
                {"field": "subject", "op": "matches_regex",
                 "value": r"(?i)(report|weekly recap|monthly summary|performance review)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "auto_reply",
                 "template": "Hi {sender_name},\n\nAttached is the latest report for {client_name}. Let me know if you need a different date range.\n\nBest,\nZen Den"},
                {"type": "tag", "value": "report-request"},
                {"type": "log", "value": "Sent report to {sender}"},
            ],
        },
        {
            "id": "tmpl_promo_questions",
            "name": "Promo questions → auto-reply",
            "description": "Handle common questions about promotions and discounts.",
            "trigger": "email",
            "conditions": [
                {"field": "body", "op": "matches_regex",
                 "value": r"(?i)(promo(tion)?|discount|coupon|sale|special offer)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "auto_reply",
                 "template": "Hi {sender_name},\n\nHere's a summary of current promotions running for {client_name}. I'll update you if anything changes.\n\nBest,\nZen Den"},
                {"type": "tag", "value": "promo"},
            ],
        },
        {
            "id": "tmpl_performance_questions",
            "name": "Performance questions → auto-reply",
            "description": "Auto-reply with metrics when someone asks about ROAS, CPC, or conversions.",
            "trigger": "email",
            "conditions": [
                {"field": "body", "op": "matches_regex",
                 "value": r"(?i)(roas|cpc|cpa|ctr|conversion|click.?through|cost.per|impressions)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "auto_reply",
                 "template": "Hi {sender_name},\n\nHere's the latest performance snapshot for {client_name}:\n\n(Zen Den will attach the live metrics table here.)\n\nBest,\nZen Den"},
                {"type": "tag", "value": "performance"},
                {"type": "log", "value": "Performance inquiry from {sender}"},
            ],
        },
        {
            "id": "tmpl_new_client_onboarding",
            "name": "New client onboarding → tag + log",
            "description": "Flag onboarding emails so the team can set up accounts quickly.",
            "trigger": "email",
            "conditions": [
                {"field": "body", "op": "matches_regex",
                 "value": r"(?i)(new client|onboarding|kickoff|welcome aboard)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "tag", "value": "onboarding"},
                {"type": "log", "value": "New client onboarding mention from {sender}"},
                {"type": "escalate"},
            ],
        },
        {
            "id": "tmpl_urgent_escalate",
            "name": "Urgent/ASAP → escalate",
            "description": "Immediately escalate anything marked urgent or ASAP.",
            "trigger": "email",
            "conditions": [
                {"field": "subject", "op": "matches_regex",
                 "value": r"(?i)(urgent|asap|critical|emergency|time.?sensitive)"},
                {"field": "body", "op": "matches_regex",
                 "value": r"(?i)(urgent|asap|critical|emergency|time.?sensitive)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "escalate"},
                {"type": "tag", "value": "urgent"},
                {"type": "log", "value": "Urgent message from {sender} escalated"},
            ],
        },
        {
            "id": "tmpl_competitor_mentions",
            "name": "Competitor mentions → tag + log",
            "description": "Track when competitors are mentioned in client communications.",
            "trigger": "email",
            "conditions": [
                {"field": "body", "op": "matches_regex",
                 "value": r"(?i)(competitor|competing|rival|alternative|switch(ing)? to)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "tag", "value": "competitor-mention"},
                {"type": "log", "value": "Competitor mentioned by {sender}: {subject}"},
            ],
        },
        {
            "id": "tmpl_billing_forward",
            "name": "Billing/invoice → forward",
            "description": "Forward billing and invoice emails to the finance team.",
            "trigger": "email",
            "conditions": [
                {"field": "subject", "op": "matches_regex",
                 "value": r"(?i)(invoice|billing|payment|receipt|overdue|statement)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "forward", "to": "finance@hawkemedia.com",
                 "template": "FYI — billing email from {sender}.\n\nOriginal subject: {subject}\n\n{body_preview}"},
                {"type": "tag", "value": "billing"},
                {"type": "log", "value": "Billing email from {sender} forwarded to finance"},
            ],
        },
        {
            "id": "tmpl_meeting_requests",
            "name": "Meeting requests → tag",
            "description": "Tag meeting and calendar-related emails for easy filtering.",
            "trigger": "email",
            "conditions": [
                {"field": "subject", "op": "matches_regex",
                 "value": r"(?i)(meeting|calendar|schedule|sync|call|zoom|huddle|standup)"},
            ],
            "condition_logic": "any",
            "actions": [
                {"type": "tag", "value": "meeting"},
                {"type": "log", "value": "Meeting request from {sender}: {subject}"},
            ],
        },
    ]
