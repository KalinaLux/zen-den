---
name: slack-faq-responder
description: Auto-reply to common paid search team questions with pre-approved answers
version: 1.0.0
author: marketing-autopilot
license: MIT
metadata:
  hermes:
    tags: [Productivity, Slack, FAQ, Paid Search]
    requires_tools: [bash]
    related_skills: [campaign-status, promo-checker]
---

# Slack FAQ Auto-Responder — Paid Search Edition

Detect common repetitive questions and respond automatically with pre-approved answers, tuned for a paid search agency team.

## When to Use

Activates on incoming Slack messages that match FAQ patterns with high confidence (>= 0.85).

## Procedure

1. Check incoming message against `config/faq-answers.json`.
2. Use semantic matching. "Where's the naming convention doc?" should match "campaign naming conventions."
3. **Confidence >= 0.85**: Auto-respond in-thread with:
   ```
   🤖 Auto-reply from [user's name]'s assistant:
   [answer]
   _If this doesn't fully answer your question, I'll flag it for [user's name]._
   ```
4. **Confidence 0.6-0.85**: Don't auto-respond. Flag for user review via DM.
5. **Campaign status questions**: Do NOT FAQ-respond. Defer to `campaign-status` or `promo-checker` skills which give live data, not canned answers.
6. Log every response to `~/.hermes/state/faq-log.jsonl`.

## Safety

- Never auto-respond to VIP senders
- Never respond to messages with negative sentiment or complaints
- Max 3 auto-responses per channel per hour
- Never give campaign performance data via FAQ — that must come from live API queries
