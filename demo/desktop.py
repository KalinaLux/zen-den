#!/usr/bin/env python3
"""
Marketing Autopilot — Desktop App

Opens as a native macOS/Windows/Linux window. No browser needed.
Double-click to run, or: python3 desktop.py

Requires: pip install pywebview
"""

import http.server
import json
import os
import sys
import threading
import urllib.parse
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from report_generator import generate_client_report
from google_ads_client import (
    build_oauth_url, exchange_code, load_gads_config, save_gads_config,
    load_tokens, save_tokens, sync_all_live_data,
)
from report_mailer import (
    load_schedules, save_schedules, send_report_email,
    build_summary_from_client, check_schedule_due,
)
from slack_bot import start_slack_bot, stop_slack_bot, get_slack_status
from email_watcher import (
    start_email_watcher, stop_email_watcher, get_email_status,
    get_drafts_queue, approve_draft, dismiss_draft,
    load_email_config, save_email_config, test_connection as test_email_connection,
)
from analytics import (
    calculate_budget_pacing, detect_anomalies, generate_meeting_prep,
    save_snapshot, get_change_log, record_action, get_time_summary,
    generate_weekly_recap,
)
from meta_ads_client import (
    build_oauth_url as meta_oauth_url, exchange_code as meta_exchange,
    load_meta_config, save_meta_config, sync_all_live_data as meta_sync,
)
from microsoft_ads_client import (
    build_oauth_url as ms_oauth_url, exchange_code as ms_exchange,
    load_msads_config, save_msads_config, sync_all_live_data as ms_sync,
)
from tiktok_ads_client import (
    build_oauth_url as tt_oauth_url, exchange_code as tt_exchange,
    load_tiktok_config, save_tiktok_config, sync_all_live_data as tt_sync,
)
import shutil
import time as _time

# ── Path resolution ──────────────────────────────────────────
# When bundled with PyInstaller, read-only assets live inside the bundle
# but writable data (settings, logs, schedules) lives in ~/Library/Application Support/

def _is_bundled():
    return getattr(sys, '_MEIPASS', None) is not None

def _bundle_dir():
    """Directory containing bundled read-only assets."""
    if _is_bundled():
        return Path(sys._MEIPASS) / "demo"
    return Path(__file__).parent

def _data_dir():
    """Writable directory for user data. Created on first run."""
    if _is_bundled():
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent

def _config_dir():
    """Config directory (writable). Copied from bundle on first run."""
    if _is_bundled():
        d = _data_dir() / "config"
        if not d.exists():
            bundle_cfg = Path(sys._MEIPASS) / "config"
            if bundle_cfg.exists():
                shutil.copytree(bundle_cfg, d)
            else:
                d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent.parent / "config"

BUNDLE_DIR = _bundle_dir()
DATA_DIR = _data_dir()
DEMO_DIR = DATA_DIR  # backwards compat for modules that import DEMO_DIR
MOCK_DATA_PATH = BUNDLE_DIR / "mock_campaigns.json"
LIVE_DATA_PATH = DATA_DIR / "live_campaigns.json"
CONFIG_DIR = _config_dir()
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
AUDIT_LOG = LOG_DIR / "demo-audit.jsonl"

# Copy writable defaults from bundle on first run
if _is_bundled():
    for fname in ("mock_campaigns.json",):
        dest = DATA_DIR / fname
        src = BUNDLE_DIR / fname
        if not dest.exists() and src.exists():
            shutil.copy2(src, dest)
    if (DATA_DIR / "mock_campaigns.json").exists():
        MOCK_DATA_PATH = DATA_DIR / "mock_campaigns.json"
    # Always ensure fresh setup_state for first launch
    setup_dest = DATA_DIR / "setup_state.json"
    if not setup_dest.exists():
        with open(setup_dest, "w") as f:
            json.dump({"completed": False, "current_step": 0, "openai_key": "", "claude_key": "", "slack_token": "", "gmail_configured": False, "active_provider": "openai"}, f, indent=2)

PORT = 18923
SETUP_PATH = DATA_DIR / "setup_state.json"

# ── Data helpers ──────────────────────────────────────────────

def load_setup():
    if SETUP_PATH.exists():
        with open(SETUP_PATH) as f:
            return json.load(f)
    return {"completed": False, "current_step": 0, "openai_key": "", "claude_key": "", "slack_token": "", "gmail_configured": False, "active_provider": "openai"}

def save_setup(data):
    with open(SETUP_PATH, "w") as f:
        json.dump(data, f, indent=2)

def load_mock_data():
    gads_cfg = load_gads_config()
    if gads_cfg.get("use_live_data") and LIVE_DATA_PATH.exists():
        with open(LIVE_DATA_PATH) as f:
            return json.load(f)
    with open(MOCK_DATA_PATH) as f:
        return json.load(f)

def save_mock_data(data):
    with open(MOCK_DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)

def load_config(name):
    path = CONFIG_DIR / name
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f) if name.endswith(".json") else f.read()

def save_config(name, content):
    path = CONFIG_DIR / name
    with open(path, "w") as f:
        if name.endswith(".json"):
            json.dump(content, f, indent=2)
        else:
            f.write(content)

def fuzzy_match(query, candidates, threshold=0.35):
    query_lower = query.lower()
    results = []
    for name in candidates:
        score = SequenceMatcher(None, query_lower, name.lower()).ratio()
        if query_lower in name.lower():
            score = max(score, 0.85)
        for word in query_lower.split():
            if word in name.lower() and len(word) > 2:
                score = max(score, 0.6)
        if score >= threshold:
            results.append((name, score))
    return sorted(results, key=lambda x: x[1], reverse=True)

def find_client(q, data):
    for c in data["clients"]:
        names = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
        for name in names:
            if name in q.lower():
                return c
    for c in data["clients"]:
        all_names = [c["name"]] + c.get("aliases", [])
        for word in q.lower().split():
            if len(word) > 3:
                for name in all_names:
                    if word in name.lower():
                        return c
    return None

def find_campaigns(query, client):
    if not query:
        return client["campaigns"]
    names = [c["name"] for c in client["campaigns"]]
    matches = fuzzy_match(query, names)
    matched_names = {m[0] for m in matches}
    return [c for c in client["campaigns"] if c["name"] in matched_names]

def classify_question(q):
    q = q.lower().strip()
    if any(w in q for w in ["digest", "briefing", "morning", "what did i miss", "catch me up"]):
        return "digest"
    if any(w in q for w in ["promo", "promotion", "discount", "coupon", "sale extension", "sitelink sale", "code "]):
        return "promo"
    if any(w in q for w in ["campaign", "turned on", "turned off", "enabled", "paused", "running", "live", "active", "status", "is the", "is our", "did we pause", "on or off"]):
        return "campaign"
    if any(w in q for w in ["all campaigns", "list campaigns", "what's running", "what campaigns"]):
        return "campaign"
    return "general"

def search_faq(question):
    """Search the FAQ database for a matching answer."""
    faqs = load_config("faq-answers.json") or []
    q = question.lower().strip()
    best_match = None
    best_score = 0
    for faq in faqs:
        for pattern in faq.get("patterns", []):
            score = SequenceMatcher(None, q, pattern.lower()).ratio()
            if q in pattern.lower() or pattern.lower() in q:
                score = max(score, 0.85)
            for word in q.split():
                if len(word) > 3 and word in pattern.lower():
                    score = max(score, 0.55)
            if score > best_score:
                best_score = score
                best_match = faq
    if best_match and best_score >= 0.45:
        return {"type": "faq", "id": best_match["id"], "category": best_match.get("category", "General"), "patterns": best_match.get("patterns", []), "answer": best_match["answer"], "confidence": round(best_score, 2)}
    return None

def handle_campaign(question, data):
    q = question.lower()
    client = find_client(q, data)
    if not client:
        return {"type": "error", "message": f"Couldn't identify the client. Available: {', '.join(c['name'] for c in data['clients'])}"}
    status_words = {"on","off","enabled","paused","running","live","active","turned","is","the","campaign","campaigns","status","what","what's","are","has","been","did","we","?","all","for","check","list"}
    client_words = set()
    for name in [client["name"].lower()] + [a.lower() for a in client.get("aliases", [])]:
        client_words.update(name.split())
    remaining = [w.strip("?.,!") for w in q.split() if w.strip("?.,!") not in status_words and w.strip("?.,!") not in client_words and len(w.strip("?.,!")) > 1]
    hint = " ".join(remaining) if remaining else None
    campaigns = find_campaigns(hint, client) if hint else client["campaigns"]
    if not campaigns:
        campaigns = client["campaigns"]
    return {"type": "campaigns", "client": client["name"], "campaigns": campaigns}

def handle_promo(question, data):
    q = question.lower()
    client = find_client(q, data)
    if not client:
        all_promos = []
        for c in data["clients"]:
            for camp in c["campaigns"]:
                for p in camp["promos"]:
                    all_promos.append({"client": c["name"], "campaign": camp["name"], "campaign_status": camp["status"], "promo": p})
        return {"type": "all_promos", "promos": all_promos}
    promos = []
    for camp in client["campaigns"]:
        for p in camp["promos"]:
            promos.append({"campaign": camp["name"], "campaign_status": camp["status"], "promo": p})
    return {"type": "client_promos", "client": client["name"], "promos": promos}

def handle_digest(data):
    now = datetime.now().strftime("%A, %B %d")
    alerts = []
    for c in data["clients"]:
        for camp in c["campaigns"]:
            for p in camp.get("promos", []):
                if p.get("status") == "DISAPPROVED":
                    alerts.append({"level": "critical", "message": f"{c['name']} | {camp['name']} — promo DISAPPROVED: {p.get('reason', '')}"})
            if camp["status"] == "PAUSED":
                alerts.append({"level": "warning", "message": f"{c['name']} | {camp['name']} — campaign is PAUSED"})
    enabled_count = sum(1 for c in data["clients"] for camp in c["campaigns"] if camp["status"] == "ENABLED")
    return {
        "type": "digest", "date": now, "alerts": alerts,
        "enabled_count": enabled_count, "client_count": len(data["clients"]),
        "urgent": [
            {"sender": "@jessicaw", "channel": "#trueform-paid", "message": "Can we increase Spring Launch budget to $750/day?", "time": "42m ago"},
            {"sender": "@client-coppervine", "channel": "#coppervine", "message": "Our wine club promo isn't showing — what's going on?", "time": "1h ago"},
        ],
        "action_needed": [
            {"sender": "@markr", "channel": "#paid-search", "message": "When are we enabling the Solara summer sale campaign?"},
            {"sender": "@amandal", "channel": "#reporting", "message": "Q1 decks due to clients by EOD Friday"},
            {"sender": "@danielm", "channel": "#solara", "message": "Client wants to add Performance Max — thoughts?"},
        ],
        "calendar": [
            {"time": "10:00am", "event": "TrueForm Weekly Sync", "attendees": "Jessica, Mark, Client"},
            {"time": "1:00pm", "event": "Paid Search Team Standup", "attendees": "Full team"},
            {"time": "3:30pm", "event": "Coppervine Q1 Review", "attendees": "Internal prep"},
        ],
    }

def audit_log(question, category, response_type):
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "asked_by": "demo-user", "question": question, "category": category, "response_type": response_type}
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

def read_audit_log():
    if not AUDIT_LOG.exists():
        return []
    entries = []
    for line in AUDIT_LOG.read_text().strip().split("\n"):
        if line.strip():
            entries.append(json.loads(line))
    return entries[-100:]


# ── HTTP Server ───────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _pdf(self, pdf_bytes, filename):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", len(pdf_bytes))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(pdf_bytes)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._html((BUNDLE_DIR / "index.html").read_text())
        elif path == "/api/setup":
            self._json(load_setup())
        elif path == "/api/data":
            self._json(load_mock_data())
        elif path == "/api/config/faq":
            self._json(load_config("faq-answers.json") or [])
        elif path == "/api/config/vip":
            self._json({"content": load_config("vip-senders.txt") or ""})
        elif path == "/api/config/access":
            self._json(load_config("access-control.json") or {})
        elif path == "/api/audit":
            self._json(read_audit_log())
        elif path == "/api/schedules":
            self._json(load_schedules())
        elif path == "/api/gads/status":
            cfg = load_gads_config()
            self._json(cfg)
        elif path == "/api/gads/auth-url":
            cfg = load_gads_config()
            if not cfg.get("client_id"):
                self._json({"error": "Save your OAuth Client ID first"}, 400)
                return
            redirect_uri = f"http://127.0.0.1:{PORT}/oauth/callback"
            url = build_oauth_url(cfg["client_id"], redirect_uri)
            self._json({"url": url})
        elif path == "/oauth/callback":
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            code = qs.get("code", [None])[0]
            error = qs.get("error", [None])[0]
            if error:
                self._html(f"<html><body style='font-family:system-ui;text-align:center;padding:60px'><h2>Authorization Failed</h2><p>{error}</p><p>Close this tab and try again.</p></body></html>")
                return
            if not code:
                self._html("<html><body style='font-family:system-ui;text-align:center;padding:60px'><h2>No auth code received</h2><p>Close this tab and try again.</p></body></html>")
                return
            cfg = load_gads_config()
            redirect_uri = f"http://127.0.0.1:{PORT}/oauth/callback"
            try:
                tokens = exchange_code(code, cfg["client_id"], cfg["client_secret"], redirect_uri)
                save_tokens(tokens)
                cfg["connected"] = True
                save_gads_config(cfg)
                audit_log("Google Ads OAuth connected", "system", "oauth")
                self._html("<html><body style='font-family:system-ui;text-align:center;padding:60px;background:#111827;color:#e8eaf0'><h2 style='color:#86efac'>✓ Connected!</h2><p style='color:#9ca3c0;margin-top:12px'>Google Ads is now linked to Zen Den.</p><p style='color:#6b7394;margin-top:8px'>You can close this tab and go back to the app.</p></body></html>")
            except Exception as e:
                self._html(f"<html><body style='font-family:system-ui;text-align:center;padding:60px'><h2>Connection Error</h2><p>{e}</p><p>Close this tab and check your credentials in Settings.</p></body></html>")
        elif path.startswith("/api/report/"):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            client_slug = urllib.parse.unquote(path[len("/api/report/"):])
            date_range = qs.get("range", ["Last 30 Days"])[0]
            data = load_mock_data()
            client = None
            for c in data["clients"]:
                names = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
                if client_slug.lower() in names:
                    client = c
                    break
            if not client:
                for c in data["clients"]:
                    if client_slug.lower() in c["name"].lower():
                        client = c
                        break
            if not client:
                self._json({"error": f"Client '{client_slug}' not found"}, 404)
                return
            try:
                pdf_bytes = generate_client_report(client, date_range)
                safe_name = client["name"].replace(" ", "_").lower()
                filename = f"{safe_name}_report_{datetime.now().strftime('%Y%m%d')}.pdf"
                audit_log(f"Generated report for {client['name']}", "report", "pdf")
                record_action(DATA_DIR, "report_generated", {"client": client["name"]})
                self._pdf(pdf_bytes, filename)
            except Exception as e:
                self._json({"error": str(e)}, 500)
        elif path == "/api/slack/status":
            self._json(get_slack_status())
        elif path == "/api/email/status":
            self._json(get_email_status())
        elif path == "/api/email/drafts":
            self._json(get_drafts_queue())
        elif path == "/api/email/config":
            self._json(load_email_config())
        elif path == "/api/pacing":
            self._json(calculate_budget_pacing(load_mock_data()))
        elif path == "/api/anomalies":
            self._json(detect_anomalies(load_mock_data()))
        elif path == "/api/changes":
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            days = int(qs.get("days", [7])[0])
            self._json(get_change_log(DATA_DIR, days))
        elif path == "/api/time-saved":
            self._json(get_time_summary(DATA_DIR))
        elif path == "/api/quick-replies":
            qr_path = BUNDLE_DIR / "quick_replies.json"
            if not qr_path.exists():
                qr_path = DATA_DIR / "quick_replies.json"
            if qr_path.exists():
                with open(qr_path) as f:
                    self._json(json.load(f))
            else:
                self._json([])
        elif path.startswith("/api/meeting-prep/"):
            client_slug = urllib.parse.unquote(path[len("/api/meeting-prep/"):])
            data = load_mock_data()
            client = None
            for c in data["clients"]:
                if client_slug.lower() in c["name"].lower():
                    client = c
                    break
            if not client:
                self._json({"error": f"Client '{client_slug}' not found"}, 404)
            else:
                brief = generate_meeting_prep(client)
                record_action(DATA_DIR, "meeting_prep", {"client": client["name"]})
                audit_log(f"Meeting prep for {client['name']}", "meeting_prep", "brief")
                self._json(brief)
        elif path == "/api/weekly-recap":
            data = load_mock_data()
            ts = get_time_summary(DATA_DIR)
            self._json(generate_weekly_recap(data, ts))
        elif path == "/api/i18n":
            i18n_path = BUNDLE_DIR / "i18n.json"
            if not i18n_path.exists():
                i18n_path = DATA_DIR / "i18n.json"
            if i18n_path.exists():
                with open(i18n_path) as f:
                    self._json(json.load(f))
            else:
                self._json({"en": {}})
        elif path == "/api/platforms":
            meta_cfg = load_meta_config()
            ms_cfg = load_msads_config()
            tt_cfg = load_tiktok_config()
            gads_cfg = load_gads_config()
            self._json({"google": {"connected": gads_cfg.get("connected", False), "use_live": gads_cfg.get("use_live_data", False)}, "meta": {"connected": meta_cfg.get("connected", False), "use_live": meta_cfg.get("use_live_data", False)}, "microsoft": {"connected": ms_cfg.get("connected", False), "use_live": ms_cfg.get("use_live_data", False)}, "tiktok": {"connected": tt_cfg.get("connected", False), "use_live": tt_cfg.get("use_live_data", False)}})
        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/schedules/send-now":
            body = self._body()
            client_name = body.get("client_name", "")
            date_range = body.get("date_range", "Last 30 Days")
            recipients = body.get("recipients", [])
            sched_data = load_schedules()
            email_cfg = sched_data.get("email_config", {})
            data = load_mock_data()
            client = None
            for c in data["clients"]:
                if c["name"].lower() == client_name.lower():
                    client = c
                    break
            if not client:
                self._json({"ok": False, "error": f"Client '{client_name}' not found"}, 404)
                return
            try:
                pdf_bytes = generate_client_report(client, date_range)
                summary = build_summary_from_client(client)
                ok, msg = send_report_email(pdf_bytes, client["name"], date_range, recipients, email_cfg, summary)
                if ok:
                    audit_log(f"Emailed report for {client['name']} to {', '.join(recipients)}", "report", "email")
                self._json({"ok": ok, "message": msg})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/schedules/test-email":
            sched_data = load_schedules()
            email_cfg = sched_data.get("email_config", {})
            sender = email_cfg.get("sender_email", "")
            if not sender:
                self._json({"ok": False, "error": "Configure sender email first"})
                return
            ok, msg = send_report_email(
                b"%PDF-1.4 test", "Test Client", "Test Period",
                [sender], email_cfg,
                {"Status": "Email is working!"},
            )
            self._json({"ok": ok, "message": msg})
            return
        if path == "/api/gads/sync":
            data, error = sync_all_live_data()
            if error:
                self._json({"ok": False, "error": error}, 400)
            else:
                with open(LIVE_DATA_PATH, "w") as f:
                    json.dump(data, f, indent=2)
                cfg = load_gads_config()
                cfg["last_sync"] = datetime.now(timezone.utc).isoformat()
                save_gads_config(cfg)
                audit_log("Synced live Google Ads data", "system", "sync")
                self._json({"ok": True, "client_count": len(data.get("clients", []))})
            return
        if path == "/api/chat":
            body = self._body()
            question = body.get("question", "")
            data = load_mock_data()
            cat = classify_question(question)
            if cat == "digest": result = handle_digest(data)
            elif cat == "promo": result = handle_promo(question, data)
            elif cat == "campaign": result = handle_campaign(question, data)
            else:
                faq_result = search_faq(question)
                if faq_result:
                    result = faq_result
                    cat = "faq"
                else:
                    result = {"type": "general", "message": "I don't have a specific answer for that yet. You can add it to the Q&A Library! I can help with campaign status, promos, budget questions, reporting, and more."}
            audit_log(question, cat, result.get("type", "unknown"))
            record_action(DATA_DIR, "faq_answered" if cat == "faq" else "campaign_check", {"question": question})
            self._json({"category": cat, "result": result})
        elif path == "/api/slack/start":
            body = self._body()
            setup = load_setup()
            bot_token = body.get("bot_token") or setup.get("slack_token", "")
            app_token = body.get("app_token", "")
            if not bot_token or not app_token:
                self._json({"ok": False, "error": "Need both Bot Token and App-Level Token"})
            else:
                access = load_config("access-control.json") or {}
                vip_raw = load_config("vip-senders.txt") or ""
                vips = [v.strip() for v in vip_raw.split("\n") if v.strip()]
                result = start_slack_bot(bot_token, app_token, load_mock_data, search_faq, audit_log, access, vips)
                self._json(result)
        elif path == "/api/slack/stop":
            stop_slack_bot()
            self._json({"ok": True})
        elif path == "/api/email/start":
            cfg = load_email_config()
            result = start_email_watcher(cfg, load_mock_data, search_faq, audit_log)
            if isinstance(result, dict) and result.get("ok") is False:
                self._json(result)
            else:
                self._json({"ok": True})
        elif path == "/api/email/stop":
            stop_email_watcher()
            self._json({"ok": True})
        elif path == "/api/email/test":
            cfg = self._body() if int(self.headers.get("Content-Length", 0)) > 0 else load_email_config()
            ok, msg = test_email_connection(cfg)
            self._json({"ok": ok, "message": msg})
        elif path == "/api/email/drafts/approve":
            body = self._body()
            ok, msg = approve_draft(body.get("draft_id", ""))
            self._json({"ok": ok, "message": msg})
        elif path == "/api/email/drafts/dismiss":
            body = self._body()
            ok, msg = dismiss_draft(body.get("draft_id", ""))
            self._json({"ok": ok, "message": msg})
        elif path == "/api/snapshot":
            data = load_mock_data()
            save_snapshot(data, DATA_DIR)
            self._json({"ok": True})
        elif path == "/api/clients/add":
            body = self._body()
            data = load_mock_data()
            new_client = {"name": body.get("name", "New Client"), "aliases": body.get("aliases", []), "customer_id": body.get("customer_id", ""), "account_lead": body.get("account_lead", ""), "campaigns": []}
            data["clients"].append(new_client)
            save_mock_data(data)
            self._json({"ok": True, "client_count": len(data["clients"])})
        elif path == "/api/clients/delete":
            body = self._body()
            name = body.get("name", "")
            data = load_mock_data()
            data["clients"] = [c for c in data["clients"] if c["name"] != name]
            save_mock_data(data)
            self._json({"ok": True})
        elif path == "/api/campaigns/add":
            body = self._body()
            client_name = body.get("client_name", "")
            data = load_mock_data()
            for c in data["clients"]:
                if c["name"] == client_name:
                    camp = {"id": f"C-{int(_time.time())}", "name": body.get("name", "New Campaign"), "status": body.get("status", "ENABLED"), "network": body.get("network", "SEARCH"), "budget_daily": body.get("budget_daily", "$0.00"), "start_date": body.get("start_date", datetime.now().strftime("%Y-%m-%d")), "end_date": body.get("end_date", "ongoing"), "promos": [], "performance": {"impressions": 0, "clicks": 0, "ctr": 0, "avg_cpc": 0, "cost": 0, "conversions": 0, "conv_rate": 0, "conv_value": 0, "roas": 0}}
                    c["campaigns"].append(camp)
                    save_mock_data(data)
                    self._json({"ok": True})
                    return
            self._json({"ok": False, "error": "Client not found"}, 404)
        elif path == "/api/campaigns/delete":
            body = self._body()
            data = load_mock_data()
            for c in data["clients"]:
                if c["name"] == body.get("client_name", ""):
                    c["campaigns"] = [x for x in c["campaigns"] if x["id"] != body.get("campaign_id", "")]
                    save_mock_data(data)
                    self._json({"ok": True})
                    return
            self._json({"ok": False, "error": "Not found"}, 404)
        else:
            self.send_error(404)

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/schedules":
            save_schedules(self._body())
            self._json({"ok": True})
            return
        if path == "/api/gads/config":
            body = self._body()
            cfg = load_gads_config()
            cfg["client_id"] = body.get("client_id", cfg.get("client_id", ""))
            cfg["client_secret"] = body.get("client_secret", cfg.get("client_secret", ""))
            cfg["developer_token"] = body.get("developer_token", cfg.get("developer_token", ""))
            cfg["mcc_customer_id"] = body.get("mcc_customer_id", cfg.get("mcc_customer_id", ""))
            save_gads_config(cfg)
            self._json({"ok": True})
            return
        if path == "/api/gads/toggle-live":
            body = self._body()
            cfg = load_gads_config()
            cfg["use_live_data"] = body.get("use_live_data", False)
            save_gads_config(cfg)
            self._json({"ok": True})
            return
        if path == "/api/setup":
            save_setup(self._body()); self._json({"ok": True})
        elif path == "/api/config/faq":
            save_config("faq-answers.json", self._body()); self._json({"ok": True})
        elif path == "/api/config/vip":
            save_config("vip-senders.txt", self._body().get("content", "")); self._json({"ok": True})
        elif path == "/api/config/access":
            save_config("access-control.json", self._body()); self._json({"ok": True})
        elif path == "/api/data":
            save_mock_data(self._body()); self._json({"ok": True})
        elif path == "/api/email/config":
            save_email_config(self._body()); self._json({"ok": True})
        elif path == "/api/quick-replies":
            qr_path = DATA_DIR / "quick_replies.json"
            with open(qr_path, "w") as f:
                json.dump(self._body(), f, indent=2)
            self._json({"ok": True})
        elif path == "/api/meta/config":
            body = self._body()
            cfg = load_meta_config()
            for k in ("app_id", "app_secret", "ad_account_id"):
                if k in body: cfg[k] = body[k]
            save_meta_config(cfg)
            self._json({"ok": True})
        elif path == "/api/microsoft/config":
            body = self._body()
            cfg = load_msads_config()
            for k in ("client_id", "client_secret", "developer_token", "account_id", "customer_id"):
                if k in body: cfg[k] = body[k]
            save_msads_config(cfg)
            self._json({"ok": True})
        elif path == "/api/tiktok/config":
            body = self._body()
            cfg = load_tiktok_config()
            for k in ("app_id", "app_secret", "advertiser_id"):
                if k in body: cfg[k] = body[k]
            save_tiktok_config(cfg)
            self._json({"ok": True})
        elif path == "/api/clients/edit":
            body = self._body()
            data = load_mock_data()
            for c in data["clients"]:
                if c["name"] == body.get("original_name", ""):
                    c["name"] = body.get("name", c["name"])
                    c["aliases"] = body.get("aliases", c.get("aliases", []))
                    c["customer_id"] = body.get("customer_id", c.get("customer_id", ""))
                    c["account_lead"] = body.get("account_lead", c.get("account_lead", ""))
                    save_mock_data(data)
                    self._json({"ok": True})
                    return
            self._json({"ok": False, "error": "Client not found"}, 404)
        else:
            self.send_error(404)

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/config/faq/"):
            faq_id = path.split("/")[-1]
            faqs = load_config("faq-answers.json") or []
            faqs = [f for f in faqs if f.get("id") != faq_id]
            save_config("faq-answers.json", faqs)
            self._json({"ok": True})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def start_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


# ── Report Scheduler ──────────────────────────────────────────

def _scheduler_loop():
    """Background loop that checks every 60s if any scheduled reports are due."""
    while True:
        try:
            sched_data = load_schedules()
            schedules = sched_data.get("schedules", [])
            email_cfg = sched_data.get("email_config", {})
            changed = False

            for entry in schedules:
                if not check_schedule_due(entry):
                    continue
                client_name = entry.get("client_name", "")
                recipients = entry.get("recipients", [])
                date_range = entry.get("date_range", "Last 30 Days")
                if not recipients:
                    continue

                data = load_mock_data()
                client = None
                for c in data["clients"]:
                    if c["name"].lower() == client_name.lower():
                        client = c
                        break
                if not client:
                    continue

                try:
                    pdf_bytes = generate_client_report(client, date_range)
                    summary = build_summary_from_client(client)
                    ok, msg = send_report_email(pdf_bytes, client["name"], date_range, recipients, email_cfg, summary)
                    if ok:
                        entry["last_sent"] = datetime.now(timezone.utc).isoformat()
                        changed = True
                        audit_log(f"[Scheduled] Emailed report for {client['name']} to {', '.join(recipients)}", "report", "scheduled_email")
                except Exception:
                    pass

            if changed:
                save_schedules(sched_data)
        except Exception:
            pass
        _time.sleep(60)


def start_scheduler():
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()


# ── Desktop Window ────────────────────────────────────────────

def main():
    try:
        import webview
    except ImportError:
        print("pywebview not installed. Installing...")
        os.system(f"{sys.executable} -m pip install pywebview")
        import webview

    # Start HTTP server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Start report scheduler
    start_scheduler()

    # Take initial data snapshot for change tracking
    try:
        save_snapshot(load_mock_data(), DATA_DIR)
    except Exception:
        pass

    # Give server a moment to start
    import time
    time.sleep(0.3)

    # Create native window
    window = webview.create_window(
        title="Zen Den",
        url=f"http://127.0.0.1:{PORT}",
        width=1280,
        height=820,
        min_size=(900, 600),
        text_select=True,
        zoomable=True,
    )

    def _on_loaded():
        """Inject a JS helper that makes file downloads work in pywebview."""
        if window:
            window.evaluate_js("""
                window.__zenDownload = function(url, filename) {
                    var x = new XMLHttpRequest();
                    x.open('GET', url, true);
                    x.responseType = 'blob';
                    x.onload = function() {
                        var a = document.createElement('a');
                        a.href = URL.createObjectURL(x.response);
                        a.download = filename;
                        a.style.display = 'none';
                        document.body.appendChild(a);
                        a.click();
                        setTimeout(function(){ document.body.removeChild(a); URL.revokeObjectURL(a.href); }, 500);
                    };
                    x.send();
                };
            """)

    window.events.loaded += _on_loaded

    webview.start(
        debug=False,
        private_mode=False,
    )

    print("Window closed. Goodbye!")
    sys.exit(0)


if __name__ == "__main__":
    main()
