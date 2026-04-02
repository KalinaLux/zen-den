"""
Slack Bot — Zen Den
Marketing Autopilot Slack integration using Socket Mode.

Watches channels for campaign/promo/FAQ questions and auto-responds.
Injected dependencies: data_loader, faq_searcher, audit_logger.
"""

import sys
import json
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    SLACK_BOLT_AVAILABLE = True
except ImportError:
    SLACK_BOLT_AVAILABLE = False

logger = logging.getLogger("zen-den.slack")

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_bot_thread: threading.Thread | None = None
_handler: object | None = None
_app: object | None = None

_running = False
_connected = False
_messages_handled = 0
_auto_replies_sent = 0
_last_message_time: str | None = None
_channels_active: set[str] = set()

_lock = threading.Lock()

# Injected callables (set by start_slack_bot)
_data_loader = None
_faq_searcher = None
_audit_logger = None
_access_control: dict | None = None
_vip_senders: list | None = None
_bot_user_id: str | None = None


# ---------------------------------------------------------------------------
# Classification (mirrors app.py logic exactly)
# ---------------------------------------------------------------------------

def classify_question(q: str) -> str:
    q = q.lower().strip()
    if any(w in q for w in [
        "digest", "briefing", "morning", "what did i miss", "catch me up",
    ]):
        return "digest"
    if any(w in q for w in [
        "promo", "promotion", "discount", "coupon",
        "sale extension", "sitelink sale", "code ",
    ]):
        return "promo"
    if any(w in q for w in [
        "campaign", "turned on", "turned off", "enabled", "paused",
        "running", "live", "active", "status", "is the", "is our",
        "did we pause", "on or off",
    ]):
        return "campaign"
    if any(w in q for w in [
        "all campaigns", "list campaigns", "what's running", "what campaigns",
    ]):
        return "campaign"
    return "general"


# ---------------------------------------------------------------------------
# Helpers — client / campaign lookup (self-contained, no sibling imports)
# ---------------------------------------------------------------------------

def _find_client(q: str, data: dict):
    q_lower = q.lower()
    for c in data.get("clients", []):
        names = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
        for name in names:
            if name in q_lower:
                return c
    for c in data.get("clients", []):
        all_names = [c["name"]] + c.get("aliases", [])
        for word in q_lower.split():
            if len(word) > 3:
                for name in all_names:
                    if word in name.lower():
                        return c
    return None


def _status_icon(status: str) -> str:
    return {
        "ENABLED": "\U0001f7e2",   # 🟢
        "PAUSED": "\U0001f7e1",    # 🟡
        "REMOVED": "\U0001f534",   # 🔴
    }.get(status, "\u26aa")        # ⚪


# ---------------------------------------------------------------------------
# Response formatters (Slack mrkdwn, not HTML)
# ---------------------------------------------------------------------------

def _format_campaigns(client_name: str, campaigns: list) -> str:
    lines = [f"\U0001f4ca *{client_name}* — {len(campaigns)} campaign{'s' if len(campaigns) != 1 else ''}:"]
    for c in campaigns:
        icon = _status_icon(c["status"])
        budget = c.get("budget_daily", "")
        budget_str = f" ({budget}/day)" if budget and budget != "$0.00" else ""
        lines.append(f"\u2022 *{c['name']}* — {icon} {c['status']}{budget_str}")
    return "\n".join(lines)


def _format_promos_for_client(client_name: str, promos: list) -> str:
    if not promos:
        return f"\U0001f3f7\ufe0f *{client_name}* — no active promotions."
    lines = [f"\U0001f3f7\ufe0f *{client_name}* — {len(promos)} promo{'s' if len(promos) != 1 else ''}:"]
    for p in promos:
        promo = p["promo"]
        serving = "\u2705 Serving" if promo.get("serving") else "\u274c Not serving"
        reason = f" — _{promo['reason']}_" if promo.get("reason") else ""
        lines.append(
            f"\u2022 *{p['campaign']}*\n"
            f"   {promo['text']} [{promo['status']}] {serving}{reason}"
        )
    return "\n".join(lines)


def _format_all_promos(promos: list) -> str:
    if not promos:
        return "\U0001f3f7\ufe0f No promotions found across any client."
    lines = [f"\U0001f3f7\ufe0f All promotions ({len(promos)} total):"]
    for p in promos:
        promo = p["promo"]
        serving = "\u2705" if promo.get("serving") else "\u274c"
        lines.append(f"\u2022 *{p['client']}* | {p['campaign']} — {promo['text']} [{promo['status']}] {serving}")
    return "\n".join(lines)


def _format_digest(digest: dict) -> str:
    lines = [
        f"\u2615 *Morning Digest — {digest['date']}*",
        f"_{digest['enabled_count']} campaigns enabled across {digest['client_count']} clients_",
        "",
    ]
    if digest.get("alerts"):
        lines.append("*\u26a0\ufe0f Alerts:*")
        for a in digest["alerts"]:
            icon = "\U0001f6a8" if a["level"] == "critical" else "\u26a0\ufe0f"
            lines.append(f"{icon} {a['message']}")
        lines.append("")
    if digest.get("urgent"):
        lines.append("*\U0001f4e8 Urgent messages:*")
        for u in digest["urgent"]:
            lines.append(f"\u2022 {u['sender']} in {u['channel']} ({u['time']}): _{u['message']}_")
        lines.append("")
    if digest.get("action_needed"):
        lines.append("*\U0001f4cb Action needed:*")
        for a in digest["action_needed"]:
            lines.append(f"\u2022 {a['sender']} in {a['channel']}: _{a['message']}_")
    return "\n".join(lines)


def _format_faq(category: str, answer: str) -> str:
    return f"\U0001f4da *{category}*\n{answer}"


FALLBACK_REPLY = "\U0001f9d8 I don't have that one yet — I'll flag it for review."


# ---------------------------------------------------------------------------
# Access control check
# ---------------------------------------------------------------------------

def _user_can_access_client(user_id: str, client_name: str) -> bool:
    if not _access_control:
        return True
    user_key = f"@{user_id}"
    if user_key not in _access_control:
        return True
    allowed = _access_control[user_key]
    return client_name in allowed


# ---------------------------------------------------------------------------
# Core message handler
# ---------------------------------------------------------------------------

def _looks_like_question(text: str) -> bool:
    """Return True if the message looks like a question we should answer."""
    if "?" in text:
        return True
    category = classify_question(text)
    return category != "general"


def _handle_message(text: str, user_id: str, channel: str) -> str | None:
    """Process a message and return the reply text, or None to stay quiet."""
    global _messages_handled, _auto_replies_sent, _last_message_time

    with _lock:
        _messages_handled += 1
        _last_message_time = datetime.now(timezone.utc).isoformat()
        _channels_active.add(channel)

    if not _looks_like_question(text):
        return None

    is_vip = False
    if _vip_senders:
        user_tag = f"@{user_id}"
        is_vip = user_tag in _vip_senders or user_id in _vip_senders

    # Try FAQ first
    if _faq_searcher:
        try:
            faq_result = _faq_searcher(text)
            if faq_result and faq_result.get("type") == "faq":
                reply = _format_faq(faq_result["category"], faq_result["answer"])
                if _audit_logger:
                    _audit_logger(text, "faq", "faq")
                with _lock:
                    _auto_replies_sent += 1
                if is_vip:
                    reply = f"\U0001f31f *VIP*\n{reply}"
                return reply
        except Exception:
            logger.exception("FAQ searcher error")

    category = classify_question(text)
    data = _data_loader() if _data_loader else {"clients": []}

    reply: str | None = None

    if category == "campaign":
        client = _find_client(text, data)
        if client:
            if not _user_can_access_client(user_id, client["name"]):
                reply = f"\U0001f512 You don't have access to *{client['name']}* data."
            else:
                reply = _format_campaigns(client["name"], client["campaigns"])
        else:
            client_names = ", ".join(c["name"] for c in data.get("clients", []))
            reply = f"Couldn't identify the client. Available: {client_names}"

    elif category == "promo":
        client = _find_client(text, data)
        if client:
            if not _user_can_access_client(user_id, client["name"]):
                reply = f"\U0001f512 You don't have access to *{client['name']}* data."
            else:
                promos = []
                for camp in client["campaigns"]:
                    for p in camp["promos"]:
                        promos.append({
                            "campaign": camp["name"],
                            "campaign_status": camp["status"],
                            "promo": p,
                        })
                reply = _format_promos_for_client(client["name"], promos)
        else:
            all_promos = []
            for c in data.get("clients", []):
                for camp in c["campaigns"]:
                    for p in camp["promos"]:
                        all_promos.append({
                            "client": c["name"],
                            "campaign": camp["name"],
                            "campaign_status": camp["status"],
                            "promo": p,
                        })
            reply = _format_all_promos(all_promos)

    elif category == "digest":
        now = datetime.now().strftime("%A, %B %d")
        alerts = []
        for c in data.get("clients", []):
            for camp in c["campaigns"]:
                for p in camp.get("promos", []):
                    if p.get("status") == "DISAPPROVED":
                        alerts.append({
                            "level": "critical",
                            "message": f"{c['name']} | {camp['name']} — promo DISAPPROVED: {p.get('reason', '')}",
                        })
                if camp["status"] == "PAUSED":
                    alerts.append({
                        "level": "warning",
                        "message": f"{c['name']} | {camp['name']} — campaign is PAUSED",
                    })
        enabled_count = sum(
            1 for c in data.get("clients", [])
            for camp in c["campaigns"]
            if camp["status"] == "ENABLED"
        )
        digest = {
            "type": "digest",
            "date": now,
            "alerts": alerts,
            "enabled_count": enabled_count,
            "client_count": len(data.get("clients", [])),
            "urgent": [],
            "action_needed": [],
        }
        reply = _format_digest(digest)

    else:
        reply = FALLBACK_REPLY

    if _audit_logger:
        try:
            _audit_logger(text, category, category if reply != FALLBACK_REPLY else "unknown")
        except Exception:
            logger.exception("Audit logger error")

    if reply:
        with _lock:
            _auto_replies_sent += 1
        if is_vip:
            reply = f"\U0001f31f *VIP*\n{reply}"

    return reply


# ---------------------------------------------------------------------------
# Bot lifecycle
# ---------------------------------------------------------------------------

_RETRY_DELAY_SECS = 5
_MAX_RETRIES = 3


def _run_bot(bot_token: str, app_token: str):
    """Entry point for the daemon thread. Starts the Slack app with retries."""
    global _running, _connected, _handler, _app, _bot_user_id

    if not SLACK_BOLT_AVAILABLE:
        logger.error("slack_bolt is not installed — cannot start Slack bot")
        with _lock:
            _running = False
            _connected = False
        return

    retries = 0
    while retries <= _MAX_RETRIES:
        try:
            _app = App(token=bot_token)

            # Resolve our own bot user ID so we can ignore our messages
            try:
                auth = _app.client.auth_test()
                _bot_user_id = auth.get("user_id")
            except Exception:
                logger.warning("Could not resolve bot user ID via auth_test")

            @_app.event("message")
            def on_message(event, say):
                user = event.get("user", "")
                text = event.get("text", "")
                channel = event.get("channel", "")
                subtype = event.get("subtype")

                if subtype is not None:
                    return
                if _bot_user_id and user == _bot_user_id:
                    return
                if not text.strip():
                    return

                try:
                    reply = _handle_message(text, user, channel)
                    if reply:
                        say(reply)
                except Exception:
                    logger.exception("Error handling Slack message")

            _handler = SocketModeHandler(_app, app_token)

            with _lock:
                _running = True
                _connected = True

            logger.info("Slack bot connected (attempt %d)", retries + 1)
            _handler.start()
            break

        except Exception:
            retries += 1
            logger.exception(
                "Slack connection failed (attempt %d/%d)",
                retries, _MAX_RETRIES + 1,
            )
            with _lock:
                _connected = False
            if retries <= _MAX_RETRIES:
                import time
                time.sleep(_RETRY_DELAY_SECS)

    with _lock:
        _running = False
        _connected = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_slack_bot(
    bot_token: str,
    app_token: str,
    data_loader,
    faq_searcher,
    audit_logger,
    access_control: dict | None = None,
    vip_senders: list | None = None,
) -> dict:
    """Start the Slack bot in a daemon thread. Returns an initial status dict."""
    global _bot_thread, _data_loader, _faq_searcher, _audit_logger
    global _access_control, _vip_senders
    global _running, _connected, _messages_handled, _auto_replies_sent
    global _last_message_time, _channels_active

    if not SLACK_BOLT_AVAILABLE:
        logger.error("slack_bolt is not installed — pip install slack_bolt")
        return {
            "running": False,
            "connected": False,
            "error": "slack_bolt not installed",
            "messages_handled": 0,
            "last_message_time": None,
            "auto_replies_sent": 0,
            "channels_active": [],
        }

    if _running:
        return get_slack_status()

    _data_loader = data_loader
    _faq_searcher = faq_searcher
    _audit_logger = audit_logger
    _access_control = access_control
    _vip_senders = vip_senders

    with _lock:
        _messages_handled = 0
        _auto_replies_sent = 0
        _last_message_time = None
        _channels_active = set()

    _bot_thread = threading.Thread(
        target=_run_bot,
        args=(bot_token, app_token),
        daemon=True,
        name="zen-den-slack-bot",
    )
    _bot_thread.start()

    # Give the thread a moment to set _running
    _bot_thread.join(timeout=1.0)

    return get_slack_status()


def stop_slack_bot() -> None:
    """Stop the Slack bot gracefully."""
    global _running, _connected, _handler

    with _lock:
        _running = False
        _connected = False

    if _handler is not None:
        try:
            _handler.close()
        except Exception:
            logger.exception("Error closing SocketModeHandler")
        _handler = None

    logger.info("Slack bot stopped")


def get_slack_status() -> dict:
    """Return current bot status."""
    with _lock:
        return {
            "running": _running,
            "connected": _connected,
            "messages_handled": _messages_handled,
            "last_message_time": _last_message_time,
            "auto_replies_sent": _auto_replies_sent,
            "channels_active": sorted(_channels_active),
        }
