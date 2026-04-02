#!/usr/bin/env python3
"""
Zen Den — Email Watcher

Monitors an IMAP inbox and auto-drafts (or auto-sends) replies to routine
questions about paid search campaigns.  Works with any provider (Gmail,
Outlook, Yahoo, corporate Exchange).

Usage:
    from email_watcher import start_email_watcher, stop_email_watcher
    start_email_watcher(config, data_loader, faq_searcher, audit_logger)
"""

import email as _email
import imaplib
import json
import logging
import smtplib
import ssl
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

log = logging.getLogger("zen.email")

# ── Path helpers ──────────────────────────────────────────────

def _data_dir():
    if getattr(sys, '_MEIPASS', None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


CONFIG_PATH = _data_dir() / "email_watcher_config.json"
DRAFTS_PATH = _data_dir() / "email_drafts.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "mode": "draft",
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "email": "",
    "password": "",
    "check_interval_seconds": 60,
    "auto_send_to_internal_only": True,
    "watch_folders": ["INBOX"],
    "ignore_from": [],
    "signature_name": "",
    "provider_presets": {
        "gmail": {
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
        },
        "outlook": {
            "imap_host": "outlook.office365.com",
            "imap_port": 993,
            "smtp_host": "smtp.office365.com",
            "smtp_port": 587,
        },
        "yahoo": {
            "imap_host": "imap.mail.yahoo.com",
            "imap_port": 993,
            "smtp_host": "smtp.mail.yahoo.com",
            "smtp_port": 587,
        },
    },
}

# ── Config persistence ────────────────────────────────────────

def load_email_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            stored = json.load(f)
        merged = {**DEFAULT_CONFIG, **stored}
        merged["provider_presets"] = {
            **DEFAULT_CONFIG["provider_presets"],
            **stored.get("provider_presets", {}),
        }
        return merged
    return dict(DEFAULT_CONFIG)


def save_email_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

# ── Drafts persistence (thread-safe) ─────────────────────────

_drafts_lock = threading.Lock()


def _load_drafts():
    with _drafts_lock:
        if DRAFTS_PATH.exists():
            with open(DRAFTS_PATH) as f:
                return json.load(f)
        return []


def _save_drafts(drafts):
    with _drafts_lock:
        with open(DRAFTS_PATH, "w") as f:
            json.dump(drafts, f, indent=2)


def _append_draft(draft):
    drafts = _load_drafts()
    drafts.append(draft)
    _save_drafts(drafts)


def get_drafts_queue():
    return [d for d in _load_drafts() if d.get("status") == "pending"]

# ── Email classification ─────────────────────────────────────

def classify_email(subject, body):
    text = (subject + " " + body[:500]).lower()
    if any(w in text for w in [
        "campaign", "turned on", "turned off", "enabled",
        "paused", "running", "live", "active", "status",
    ]):
        return "campaign"
    if any(w in text for w in [
        "promo", "promotion", "discount", "coupon", "sale",
    ]):
        return "promo"
    if any(w in text for w in [
        "budget", "spend", "cost", "how much", "pacing",
    ]):
        return "budget"
    if any(w in text for w in [
        "report", "deck", "numbers", "performance", "metrics", "results",
    ]):
        return "reporting"
    if any(w in text for w in [
        "when", "schedule", "timeline", "deadline", "due",
    ]):
        return "scheduling"
    return "general"

# ── Email parsing helpers ─────────────────────────────────────

def _decode_header_value(raw):
    if raw is None:
        return ""
    parts = decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _extract_body(msg):
    """Return the plain-text body from a (possibly multipart) email."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return _strip_html(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                return _strip_html(text)
            return text
    return ""


def _strip_html(html):
    """Naive HTML-to-text: strip tags, collapse whitespace."""
    import re
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_sender(msg):
    """Return (name, email_address) from the From header."""
    raw = _decode_header_value(msg.get("From", ""))
    if "<" in raw and ">" in raw:
        name_part = raw.split("<")[0].strip().strip('"').strip("'")
        addr = raw.split("<")[1].split(">")[0].strip()
        return name_part or addr.split("@")[0], addr
    return raw.split("@")[0], raw.strip()


def _first_name(full_name):
    return full_name.split()[0] if full_name.strip() else "there"

# ── Reply generation ──────────────────────────────────────────

def _build_reply(category, sender_name, subject, body, data_loader,
                 faq_searcher, signature_name=""):
    """Generate a reply body and confidence score for the given email."""
    first = _first_name(sender_name)
    greeting = f"Hi {first},"
    sign_off = f"Let me know if you need anything else!\n\nBest,\n{signature_name}" if signature_name else "Let me know if you need anything else!\n\nBest regards"

    confidence = 0.5
    answer_lines = []

    if category == "campaign" and data_loader:
        try:
            data = data_loader()
            mentioned = _find_mentioned_campaigns(subject + " " + body, data)
            if mentioned:
                confidence = 0.85
                for camp in mentioned:
                    status = camp.get("status", "unknown").upper()
                    answer_lines.append(
                        f"The {camp['name']} campaign is currently {status}."
                    )
            else:
                confidence = 0.6
                answer_lines.append(
                    "I checked all active campaigns — could you clarify which "
                    "one you're asking about so I can pull the exact status?"
                )
        except Exception as exc:
            log.warning("data_loader failed: %s", exc)
            answer_lines.append(
                "Let me pull the latest campaign data and get back to you shortly."
            )
            confidence = 0.4

    elif category == "budget" and data_loader:
        try:
            data = data_loader()
            mentioned = _find_mentioned_campaigns(subject + " " + body, data)
            if mentioned:
                confidence = 0.8
                for camp in mentioned:
                    budget = camp.get("budget", "N/A")
                    spend = camp.get("spend", camp.get("cost", "N/A"))
                    answer_lines.append(
                        f"{camp['name']}: budget ${budget}, spend-to-date ${spend}."
                    )
            else:
                confidence = 0.55
                answer_lines.append(
                    "Could you let me know which campaign or client you'd "
                    "like budget details for?"
                )
        except Exception as exc:
            log.warning("data_loader failed: %s", exc)
            answer_lines.append(
                "I'm pulling the latest budget numbers — I'll follow up shortly."
            )
            confidence = 0.4

    elif category == "reporting":
        confidence = 0.7
        answer_lines.append(
            "I'll get the latest performance report generated and sent over "
            "to you shortly. If you need a specific date range or metrics, "
            "just let me know!"
        )

    elif category == "scheduling":
        confidence = 0.6
        answer_lines.append(
            "Let me check on the timeline and get back to you with the details."
        )

    elif category == "promo":
        confidence = 0.65
        answer_lines.append(
            "I'll review the promo details and get everything updated. "
            "I'll confirm once the changes are live."
        )

    if faq_searcher and not answer_lines:
        try:
            faq_result = faq_searcher(subject + " " + body[:300])
            if faq_result:
                answer_lines.append(faq_result)
                confidence = max(confidence, 0.7)
        except Exception as exc:
            log.warning("faq_searcher failed: %s", exc)

    if not answer_lines:
        confidence = 0.35
        answer_lines.append(
            "Thanks for your email — let me look into this and get back "
            "to you shortly."
        )

    body_text = "\n\n".join(answer_lines)
    reply = f"{greeting}\n\n{body_text}\n\n{sign_off}"
    return reply, confidence


def _find_mentioned_campaigns(text, data):
    """Fuzzy-match campaign names mentioned in the email text."""
    text_lower = text.lower()
    found = []
    for client in data.get("clients", []):
        for camp in client.get("campaigns", []):
            name = camp.get("name", "")
            name_lower = name.lower()
            words = [w for w in name_lower.replace("|", " ").split() if len(w) > 2]
            match_count = sum(1 for w in words if w in text_lower)
            if match_count >= 2 or name_lower in text_lower:
                found.append(camp)
    return found

# ── IMAP connection ───────────────────────────────────────────

def test_connection(config):
    """Test IMAP connectivity. Returns (ok: bool, message: str)."""
    try:
        ctx = ssl.create_default_context()
        imap = imaplib.IMAP4_SSL(
            config.get("imap_host", "imap.gmail.com"),
            config.get("imap_port", 993),
            ssl_context=ctx,
        )
        imap.login(config["email"], config["password"])
        imap.select("INBOX", readonly=True)
        imap.close()
        imap.logout()
        return True, "Connection successful."
    except imaplib.IMAP4.error as exc:
        return False, f"IMAP auth error: {exc}"
    except Exception as exc:
        return False, f"Connection failed: {exc}"

# ── SMTP send helper ─────────────────────────────────────────

def _smtp_send(config, to_addr, subject, body_text):
    ctx = ssl.create_default_context()
    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
        server.login(config["email"], config["password"])

        msg = MIMEMultipart("alternative")
        msg["From"] = config["email"]
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        server.sendmail(config["email"], [to_addr], msg.as_string())

# ── Watcher state ─────────────────────────────────────────────

class _WatcherState:
    def __init__(self):
        self.running = False
        self.connected = False
        self.thread = None
        self.stop_event = threading.Event()
        self.emails_scanned = 0
        self.drafts_created = 0
        self.auto_sent = 0
        self.last_check = None
        self.errors = []
        self.config = None
        self.data_loader = None
        self.faq_searcher = None
        self.audit_logger = None


_state = _WatcherState()
_MAX_ERRORS = 50

# ── Core polling loop ─────────────────────────────────────────

def _poll_once(imap_conn):
    """Fetch unseen messages from all watched folders, process each."""
    folders = _state.config.get("watch_folders", ["INBOX"])
    ignore_from = {a.lower() for a in _state.config.get("ignore_from", [])}

    for folder in folders:
        try:
            status, _ = imap_conn.select(folder, readonly=False)
            if status != "OK":
                log.warning("Could not select folder %s", folder)
                continue
        except Exception as exc:
            log.warning("Error selecting folder %s: %s", folder, exc)
            continue

        _, msg_ids = imap_conn.search(None, "UNSEEN")
        ids = msg_ids[0].split()
        if not ids:
            continue

        log.info("Found %d unseen message(s) in %s", len(ids), folder)

        for mid in ids:
            try:
                _, raw = imap_conn.fetch(mid, "(RFC822)")
                if not raw or not raw[0] or raw[0] is None:
                    continue
                raw_email = raw[0][1]
                msg = _email.message_from_bytes(raw_email)

                sender_name, sender_addr = _extract_sender(msg)
                if sender_addr.lower() in ignore_from:
                    log.debug("Ignoring email from %s", sender_addr)
                    continue

                subject = _decode_header_value(msg.get("Subject", ""))
                body = _extract_body(msg)

                _state.emails_scanned += 1
                category = classify_email(subject, body)

                reply_subject = subject
                if not reply_subject.lower().startswith("re:"):
                    reply_subject = f"Re: {subject}"

                reply_body, confidence = _build_reply(
                    category, sender_name, subject, body,
                    _state.data_loader, _state.faq_searcher,
                    _state.config.get("signature_name", ""),
                )

                mode = _state.config.get("mode", "draft")
                auto_send_internal = _state.config.get(
                    "auto_send_to_internal_only", True
                )

                should_send = (
                    mode == "auto-send"
                    and confidence >= 0.7
                    and (not auto_send_internal or _is_internal(sender_addr))
                )

                draft = {
                    "id": f"draft_{uuid.uuid4().hex[:12]}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "from_email": sender_addr,
                    "from_name": sender_name,
                    "subject": reply_subject,
                    "original_body": body[:2000],
                    "draft_reply": reply_body,
                    "category": category,
                    "confidence": round(confidence, 2),
                    "status": "pending",
                }

                if should_send:
                    try:
                        _smtp_send(_state.config, sender_addr,
                                   reply_subject, reply_body)
                        draft["status"] = "sent"
                        _state.auto_sent += 1
                        log.info("Auto-sent reply to %s", sender_addr)
                    except Exception as exc:
                        log.error("SMTP send failed for %s: %s",
                                  sender_addr, exc)
                        draft["status"] = "pending"
                        _record_error(f"Send failed: {exc}")

                _append_draft(draft)
                if draft["status"] == "pending":
                    _state.drafts_created += 1

                if _state.audit_logger:
                    try:
                        _state.audit_logger(
                            "email_watcher",
                            f"Processed email from {sender_addr}: "
                            f"category={category}, "
                            f"action={'sent' if draft['status'] == 'sent' else 'drafted'}",
                        )
                    except Exception:
                        pass

                imap_conn.store(mid, "+FLAGS", "\\Seen")

            except Exception as exc:
                log.error("Error processing message %s: %s", mid, exc)
                _record_error(f"Processing error: {exc}")


def _is_internal(addr):
    """Heuristic: treat same-domain addresses as internal."""
    own = _state.config.get("email", "")
    if "@" in own and "@" in addr:
        return addr.split("@")[1].lower() == own.split("@")[1].lower()
    return False


def _record_error(msg):
    _state.errors.append(msg)
    if len(_state.errors) > _MAX_ERRORS:
        _state.errors = _state.errors[-_MAX_ERRORS:]


def _watcher_loop():
    """Main loop: connect → poll → sleep → repeat."""
    retry_delay = 10
    max_retry = 300

    while not _state.stop_event.is_set():
        imap_conn = None
        try:
            ctx = ssl.create_default_context()
            imap_conn = imaplib.IMAP4_SSL(
                _state.config["imap_host"],
                _state.config.get("imap_port", 993),
                ssl_context=ctx,
            )
            imap_conn.login(
                _state.config["email"],
                _state.config["password"],
            )
            _state.connected = True
            retry_delay = 10
            log.info("IMAP connected to %s", _state.config["imap_host"])

            while not _state.stop_event.is_set():
                try:
                    imap_conn.noop()
                except Exception:
                    log.warning("IMAP connection lost, reconnecting…")
                    break

                _poll_once(imap_conn)
                _state.last_check = datetime.now(timezone.utc).isoformat()

                interval = _state.config.get("check_interval_seconds", 60)
                if _state.stop_event.wait(timeout=interval):
                    break

        except Exception as exc:
            _state.connected = False
            msg = f"IMAP error: {exc}"
            log.error(msg)
            _record_error(msg)
            if _state.stop_event.wait(timeout=retry_delay):
                break
            retry_delay = min(retry_delay * 2, max_retry)

        finally:
            if imap_conn is not None:
                try:
                    imap_conn.close()
                except Exception:
                    pass
                try:
                    imap_conn.logout()
                except Exception:
                    pass
            _state.connected = False

    _state.running = False
    log.info("Email watcher stopped.")

# ── Public API ────────────────────────────────────────────────

def start_email_watcher(config, data_loader=None, faq_searcher=None,
                        audit_logger=None):
    if _state.running:
        log.warning("Email watcher is already running.")
        return

    _state.config = config
    _state.data_loader = data_loader
    _state.faq_searcher = faq_searcher
    _state.audit_logger = audit_logger
    _state.stop_event.clear()
    _state.running = True
    _state.emails_scanned = 0
    _state.drafts_created = 0
    _state.auto_sent = 0
    _state.last_check = None
    _state.errors = []

    t = threading.Thread(target=_watcher_loop, daemon=True, name="EmailWatcher")
    t.start()
    _state.thread = t
    log.info("Email watcher started (mode=%s).", config.get("mode", "draft"))


def stop_email_watcher():
    if not _state.running:
        return
    _state.stop_event.set()
    if _state.thread is not None:
        _state.thread.join(timeout=15)
    _state.running = False
    _state.connected = False
    log.info("Email watcher stop requested.")


def get_email_status():
    pending = len(get_drafts_queue())
    return {
        "running": _state.running,
        "connected": _state.connected,
        "emails_scanned": _state.emails_scanned,
        "drafts_pending": pending,
        "auto_sent": _state.auto_sent,
        "last_check": _state.last_check,
        "errors": list(_state.errors[-10:]),
    }


def approve_draft(draft_id):
    """Send a pending draft and update its status."""
    drafts = _load_drafts()
    for d in drafts:
        if d["id"] == draft_id and d["status"] == "pending":
            cfg = _state.config or load_email_config()
            try:
                _smtp_send(cfg, d["from_email"], d["subject"], d["draft_reply"])
                d["status"] = "sent"
                _save_drafts(drafts)
                _state.auto_sent += 1
                log.info("Approved & sent draft %s to %s",
                         draft_id, d["from_email"])
                return True, "Sent successfully."
            except Exception as exc:
                log.error("Failed to send draft %s: %s", draft_id, exc)
                return False, f"Send failed: {exc}"
    return False, "Draft not found or already processed."


def dismiss_draft(draft_id):
    """Remove a draft from the pending queue."""
    drafts = _load_drafts()
    for d in drafts:
        if d["id"] == draft_id and d["status"] == "pending":
            d["status"] = "dismissed"
            _save_drafts(drafts)
            log.info("Dismissed draft %s", draft_id)
            return True
    return False
