---
name: slack-triage
description: Categorize incoming Slack messages by urgency for a paid search team lead
version: 1.0.0
author: marketing-autopilot
license: MIT
metadata:
  hermes:
    tags: [Productivity, Slack, Paid Search, Triage]
    requires_tools: [bash]
---

# Slack Triage — Paid Search Edition

Monitor Slack channels and classify every message by urgency, tuned for the day-to-day of running paid search at an agency.

## When to Use

Activates automatically on every incoming Slack message in monitored channels. Also triggered manually: "triage my Slack" or "what did I miss?"

## Classification Categories

| Category | Criteria for a Paid Search AD |
|----------|-------------------------------|
| **urgent** | Campaign status questions from clients or leadership, budget alerts, disapproved ads, account suspensions, pacing issues, "ASAP" anything |
| **action-needed** | Team questions about campaign setup, optimization requests, report requests, promo activation asks, anything requiring a decision |
| **fyi** | Status updates, shared reports, team announcements, meeting notes, industry news |
| **noise** | Bot notifications for routine events, emoji reactions, social chatter, messages in channels you're only monitoring |

## Procedure

1. When a Slack message arrives, read the content, sender, channel, and thread context.
2. Check if it's a **campaign status question** (e.g., "is X turned on?"). If yes, defer to the `campaign-status` or `promo-checker` skill instead of just triaging it.
3. Otherwise, classify using the categories above. Agency-specific escalation rules:
   - Client-facing Slack channels → always `action-needed` minimum
   - Messages from anyone in `config/vip-senders.txt` → always `action-needed` minimum
   - Keywords: "pacing", "overspend", "disapproved", "suspended", "budget" → `urgent`
   - Keywords: "report", "deck", "presentation" → `action-needed`
4. Append to `~/.hermes/state/slack-triage-log.jsonl`:
   ```json
   {"ts": "...", "channel": "#paid-search", "sender": "alice", "category": "urgent", "summary": "Client asking about budget pacing for Nike", "message_link": "..."}
   ```
5. If `urgent`, notify the user immediately via DM.

## Pitfalls

- Don't triage messages that the `campaign-status` or `promo-checker` skills should handle directly. If someone asks "is the campaign on?", that's a status check, not just triage.
- Client names in messages may be informal ("the shoe client" vs "Nike"). Cross-reference `config/client-accounts.json` for aliases.
