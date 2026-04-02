#!/usr/bin/env python3
"""
Marketing Autopilot — Web Dashboard & Chat Demo

Run:  python3 app.py
Open: http://localhost:8000

Zero external dependencies — uses Python stdlib only.
"""

import http.server
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

PORT = 8000
DEMO_DIR = Path(__file__).parent
MOCK_DATA_PATH = DEMO_DIR / "mock_campaigns.json"
CONFIG_DIR = DEMO_DIR.parent / "config"
LOG_DIR = DEMO_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
AUDIT_LOG = LOG_DIR / "demo-audit.jsonl"

def load_mock_data():
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
        if name.endswith(".json"):
            return json.load(f)
        return f.read()

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
        "type": "digest",
        "date": now,
        "alerts": alerts,
        "enabled_count": enabled_count,
        "client_count": len(data["clients"]),
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


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/index.html":
            html_path = DEMO_DIR / "index.html"
            self._send_html(html_path.read_text())

        elif path == "/api/data":
            self._send_json(load_mock_data())

        elif path == "/api/config/faq":
            self._send_json(load_config("faq-answers.json") or [])

        elif path == "/api/config/vip":
            self._send_json({"content": load_config("vip-senders.txt") or ""})

        elif path == "/api/config/access":
            self._send_json(load_config("access-control.json") or {})

        elif path == "/api/audit":
            self._send_json(read_audit_log())

        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/chat":
            body = self._read_body()
            question = body.get("question", "")
            data = load_mock_data()
            category = classify_question(question)

            if category == "digest":
                result = handle_digest(data)
            elif category == "promo":
                result = handle_promo(question, data)
            elif category == "campaign":
                result = handle_campaign(question, data)
            else:
                result = {"type": "general", "message": "I can help with campaign status checks, promo checks, and daily digests. Try asking 'Is the Solara brand campaign on?' or 'Show me all promos'."}

            audit_log(question, category, result.get("type", "unknown"))
            self._send_json({"category": category, "result": result})

        else:
            self.send_error(404)

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/config/faq":
            save_config("faq-answers.json", self._read_body())
            self._send_json({"ok": True})

        elif path == "/api/config/vip":
            body = self._read_body()
            save_config("vip-senders.txt", body.get("content", ""))
            self._send_json({"ok": True})

        elif path == "/api/config/access":
            save_config("access-control.json", self._read_body())
            self._send_json({"ok": True})

        elif path == "/api/data":
            save_mock_data(self._read_body())
            self._send_json({"ok": True})

        else:
            self.send_error(404)


def main():
    server = http.server.HTTPServer(("", PORT), Handler)
    print(f"""
  ╔═══════════════════════════════════════════════╗
  ║   Marketing Autopilot — Web Dashboard         ║
  ║                                               ║
  ║   Running at: http://localhost:{PORT}           ║
  ║   Press Ctrl+C to stop                        ║
  ╚═══════════════════════════════════════════════╝
""")

    import webbrowser
    webbrowser.open(f"http://localhost:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()

if __name__ == "__main__":
    main()
