#!/usr/bin/env python3
"""
Marketing Autopilot — Interactive Demo

Simulates the Hermes Agent + Slack experience using mock campaign data.
No API keys, no Hermes installation needed. Just run it.

Usage: python3 demo.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

DEMO_DIR = Path(__file__).parent
MOCK_DATA = DEMO_DIR / "mock_campaigns.json"

BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

def load_mock_data():
    with open(MOCK_DATA) as f:
        return json.load(f)

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

def find_client(query, data):
    for client in data["clients"]:
        names = [client["name"].lower()] + [a.lower() for a in client.get("aliases", [])]
        for name in names:
            if query.lower() in name or name in query.lower():
                return client
        matches = fuzzy_match(query, [client["name"]] + client.get("aliases", []))
        if matches:
            return client
    return None

def find_campaigns(query, client):
    if not query:
        return client["campaigns"]
    names = [c["name"] for c in client["campaigns"]]
    matches = fuzzy_match(query, names)
    matched_names = {m[0] for m in matches}
    return [c for c in client["campaigns"] if c["name"] in matched_names]

def format_status(status):
    if status == "ENABLED":
        return f"{GREEN}● ENABLED (live){RESET}"
    elif status == "PAUSED":
        return f"{YELLOW}● PAUSED{RESET}"
    elif status == "REMOVED":
        return f"{RED}● REMOVED{RESET}"
    return f"{DIM}● {status}{RESET}"

def format_promo_status(promo):
    if promo.get("status") == "DISAPPROVED":
        return f"{RED}✗ DISAPPROVED{RESET}"
    elif promo.get("serving"):
        return f"{GREEN}✓ SERVING{RESET}"
    else:
        return f"{YELLOW}○ NOT SERVING{RESET}"

def handle_campaign_status(question, data):
    """Handle 'is campaign X on?' type questions."""
    q = question.lower()

    client = None
    for c in data["clients"]:
        names = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
        for name in names:
            if name in q:
                client = c
                break
        if client:
            break

    if not client:
        for c in data["clients"]:
            all_names = [c["name"]] + c.get("aliases", [])
            for word in q.split():
                if len(word) > 3:
                    for name in all_names:
                        if word in name.lower():
                            client = c
                            break
                if client:
                    break
            if client:
                break

    if not client:
        return f"I couldn't identify which client you're asking about. Available clients: {', '.join(c['name'] for c in data['clients'])}"

    campaign_hint = None
    status_words = {"on", "off", "enabled", "paused", "running", "live", "active", "turned", "is", "the", "campaign", "campaigns", "status", "what", "what's", "are", "has", "been", "did", "we", "?", "all", "for", "check", "list"}
    client_words = set()
    for name in [client["name"].lower()] + [a.lower() for a in client.get("aliases", [])]:
        client_words.update(name.split())

    remaining_words = [w.strip("?.,!") for w in q.split() if w.strip("?.,!").lower() not in status_words and w.strip("?.,!").lower() not in client_words and len(w.strip("?.,!")) > 1]
    if remaining_words:
        campaign_hint = " ".join(remaining_words)

    if campaign_hint and campaign_hint.strip():
        campaigns = find_campaigns(campaign_hint, client)
    else:
        campaigns = client["campaigns"]

    if not campaigns:
        return f"No campaigns found matching '{campaign_hint}' for {client['name']}. Here are all their campaigns:\n\n" + format_campaign_list(client["campaigns"], client["name"])

    if len(campaigns) == 1:
        c = campaigns[0]
        lines = [f"{BOLD}{client['name']}{RESET} — {c['name']}"]
        lines.append(f"  Status: {format_status(c['status'])}")
        lines.append(f"  Budget: {c['budget_daily']}/day")
        lines.append(f"  Network: {c['network']}")
        lines.append(f"  Running: {c['start_date']} → {c['end_date']}")
        if c["promos"]:
            lines.append(f"\n  Promotions:")
            for p in c["promos"]:
                lines.append(f"    {format_promo_status(p)} {p['text']}")
                if p.get("reason"):
                    lines.append(f"      ↳ {DIM}{p['reason']}{RESET}")
        return "\n".join(lines)
    else:
        return format_campaign_list(campaigns, client["name"])

def format_campaign_list(campaigns, client_name):
    lines = [f"{BOLD}{client_name}{RESET} — {len(campaigns)} campaigns:\n"]
    for c in campaigns:
        lines.append(f"  {format_status(c['status'])}  {c['name']}")
        lines.append(f"    {DIM}Budget: {c['budget_daily']}/day | {c['network']} | {c['start_date']} → {c['end_date']}{RESET}")
        if c["promos"]:
            for p in c["promos"]:
                lines.append(f"    {format_promo_status(p)} Promo: {p['text']}")
                if p.get("reason"):
                    lines.append(f"      ↳ {DIM}{p['reason']}{RESET}")
    return "\n".join(lines)

def handle_promo_check(question, data):
    """Handle 'is the promo applied?' type questions."""
    q = question.lower()

    client = None
    for c in data["clients"]:
        names = [c["name"].lower()] + [a.lower() for a in c.get("aliases", [])]
        for name in names:
            if name in q:
                client = c
                break
        if client:
            break

    if not client:
        all_promos = []
        for c in data["clients"]:
            for camp in c["campaigns"]:
                for p in camp["promos"]:
                    all_promos.append((c["name"], camp["name"], camp["status"], p))
        if not all_promos:
            return "No promotions found across any client accounts."
        lines = [f"{BOLD}All Active Promotions Across Clients:{RESET}\n"]
        for client_name, camp_name, camp_status, p in all_promos:
            lines.append(f"  {format_promo_status(p)} {client_name} → {camp_name}")
            lines.append(f"    {p['text']}")
            if p.get("reason"):
                lines.append(f"    ↳ {DIM}{p['reason']}{RESET}")
            lines.append("")
        return "\n".join(lines)

    promos_found = []
    for camp in client["campaigns"]:
        for p in camp["promos"]:
            promos_found.append((camp, p))

    if not promos_found:
        return f"No promotion extensions found for {client['name']}. None of their {len(client['campaigns'])} campaigns have promos attached."

    lines = [f"{BOLD}{client['name']}{RESET} — {len(promos_found)} promotion(s) found:\n"]
    for camp, p in promos_found:
        lines.append(f"  Campaign: {camp['name']} ({format_status(camp['status'])})")
        lines.append(f"  {format_promo_status(p)} {p['text']}")
        if p.get("reason"):
            lines.append(f"    ↳ {DIM}{p['reason']}{RESET}")
        if p.get("start_date"):
            lines.append(f"    {DIM}Promo period: {p.get('start_date', '?')} → {p.get('end_date', '?')}{RESET}")
        lines.append("")
    return "\n".join(lines)

def handle_digest(data):
    """Generate a mock morning digest."""
    now = datetime.now().strftime("%A, %B %d")
    lines = [
        f"\n{BOLD}☀️  MORNING BRIEFING — {now}{RESET}\n",
        f"{BOLD}━━ CAMPAIGN ALERTS ━━{RESET}",
        f"  {RED}🔴{RESET} Coppervine | Wine Club Promo — promotion extension {RED}DISAPPROVED{RESET} by Google",
        f"  {YELLOW}🟡{RESET} TrueForm | Non-Brand | CA — campaign is {YELLOW}PAUSED{RESET}, was it intentional?",
        f"  {GREEN}🟢{RESET} All other accounts healthy (6 campaigns active across 3 clients)",
        "",
        f"{BOLD}━━ URGENT (respond today) ━━{RESET}",
        f"  • {BOLD}@jessicaw{RESET} in #trueform-paid: \"Can we increase Spring Launch budget to $750/day?\" — 42m ago",
        f"  • {BOLD}@client-coppervine{RESET} in #coppervine: \"Our wine club promo isn't showing — what's going on?\" — 1h ago",
        "",
        f"{BOLD}━━ ACTION NEEDED ━━{RESET}",
        f"  • {BOLD}@markr{RESET} in #paid-search: \"When are we enabling the Solara summer sale campaign?\"",
        f"  • {BOLD}@amandal{RESET} in #reporting: \"Q1 decks due to clients by EOD Friday\"",
        f"  • {BOLD}@danielm{RESET} in #solara: \"Client wants to add Performance Max — thoughts?\"",
        "",
        f"{BOLD}━━ TODAY'S CALENDAR ━━{RESET}",
        f"  • 10:00am — TrueForm Weekly Sync (Jessica, Mark, Client)",
        f"  • 1:00pm — Paid Search Team Standup",
        f"  • 3:30pm — Coppervine Q1 Review (Internal Prep)",
        "",
        f"{BOLD}━━ FYI ━━{RESET}",
        f"  • 12 messages in #general — team lunch plans, nothing actionable",
        f"  • 5 messages in #industry-news — Google Ads rolling out new asset types",
        "",
        f"{BOLD}━━ STATS ━━{RESET}",
        f"  Messages since last digest: 47 (Urgent: 2 | Action: 3 | FYI: 17 | Noise: 25)",
        f"  Campaign status checks answered by AI yesterday: 8",
    ]
    return "\n".join(lines)

def classify_question(question):
    """Determine what type of question this is."""
    q = question.lower().strip()

    if any(w in q for w in ["digest", "briefing", "morning", "what did i miss", "catch me up"]):
        return "digest"

    if any(w in q for w in ["promo", "promotion", "discount", "coupon", "sale extension", "sitelink sale", "code "]):
        return "promo"

    if any(w in q for w in ["campaign", "turned on", "turned off", "enabled", "paused", "running", "live", "active", "status", "is the", "is our", "did we pause", "on or off"]):
        return "campaign"

    if any(w in q for w in ["all campaigns", "list campaigns", "what's running", "what campaigns"]):
        return "campaign"

    if q in ["help", "?", "commands"]:
        return "help"

    return "general"

def print_help():
    lines = [
        f"\n{BOLD}Marketing Autopilot — Demo Commands{RESET}\n",
        f"  Try asking questions like your friend's team would on Slack:\n",
        f"  {CYAN}Campaign Status:{RESET}",
        f"    \"Is the Solara brand campaign on?\"",
        f"    \"What campaigns are running for TrueForm?\"",
        f"    \"Did we pause TrueForm non-brand?\"",
        f"    \"Is the Coppervine wine club campaign live?\"",
        f"    \"Status of all Solara campaigns\"",
        "",
        f"  {CYAN}Promo Checks:{RESET}",
        f"    \"Has the promo been applied to TrueForm Spring Launch?\"",
        f"    \"Is the Solara summer sale promo active?\"",
        f"    \"What promos are running for Coppervine?\"",
        f"    \"Show me all active promos\"",
        "",
        f"  {CYAN}Morning Digest:{RESET}",
        f"    \"Give me my digest\"",
        f"    \"What did I miss?\"",
        "",
        f"  {CYAN}Demo Clients:{RESET}",
        f"    • Solara Skincare (4 campaigns, 1 promo)",
        f"    • TrueForm Athletics (5 campaigns, 2 promos + 1 sitelink)",
        f"    • Coppervine Wines (3 campaigns, 1 DISAPPROVED promo)",
        "",
        f"  Type {BOLD}quit{RESET} or {BOLD}exit{RESET} to leave.\n",
    ]
    return "\n".join(lines)

def audit_log(question, category, response_preview):
    """Write to local audit log."""
    log_dir = DEMO_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "demo-audit.jsonl"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "asked_by": "demo-user",
        "question": question,
        "category": category,
        "response_length": len(response_preview),
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

def main():
    data = load_mock_data()

    print(f"""
{BOLD}╔══════════════════════════════════════════════════════╗
║        Marketing Autopilot — Interactive Demo        ║
║                                                      ║
║  Simulating: Hermes Agent + Slack                    ║
║  Role: Associate Director of Paid Search             ║
║  Agency: Hawke Media (demo data)                     ║
║  LLM: ChatGPT (simulated locally)                    ║
║                                                      ║
║  3 mock clients · 12 campaigns · 4 promotions        ║
║  Type 'help' for example questions                   ║
╚══════════════════════════════════════════════════════════╝{RESET}
""")

    while True:
        try:
            question = input(f"{BLUE}{BOLD}#paid-search @you:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Session ended.{RESET}")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print(f"\n{DIM}Session ended. Audit log saved to demo/logs/demo-audit.jsonl{RESET}")
            break

        category = classify_question(question)

        print(f"\n{DIM}  ⚙ Hermes: parsing intent...{RESET}")
        print(f"{DIM}  ⚙ Category: {category}{RESET}")

        if category == "help":
            response = print_help()
        elif category == "digest":
            print(f"{DIM}  ⚙ Running: slack-triage → campaign-status → daily-digest{RESET}")
            response = handle_digest(data)
        elif category == "promo":
            print(f"{DIM}  ⚙ Running: promo-checker → Google Ads API (mock){RESET}")
            response = handle_promo_check(question, data)
        elif category == "campaign":
            print(f"{DIM}  ⚙ Running: campaign-status → Google Ads API (mock){RESET}")
            response = handle_campaign_status(question, data)
        else:
            response = f"I'm not sure what you're asking. Try asking about a campaign status, promo, or type 'help' for examples."
            print(f"{DIM}  ⚙ No matching skill — would fall back to general LLM response{RESET}")

        audit_log(question, category, response)

        print(f"\n{GREEN}{BOLD}🤖 Assistant:{RESET}")
        print(response)
        print()

if __name__ == "__main__":
    main()
