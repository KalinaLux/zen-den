---
name: daily-digest
description: Morning briefing with prioritized Slack messages, emails, and campaign alerts
version: 1.0.0
author: marketing-autopilot
license: MIT
metadata:
  hermes:
    tags: [Productivity, Digest, Paid Search, Agency]
    requires_tools: [bash]
    related_skills: [slack-triage, campaign-status]
---

# Daily Digest — Paid Search Morning Briefing

Deliver a concise morning briefing via Slack DM with everything the user needs to start their day as an AD of Paid Search.

## When to Use

Runs automatically at 8:30am on weekdays. Also triggered manually: "give me my digest" or "what did I miss?"

## Digest Format

```
☀️ MORNING BRIEFING — [Day, Month Date]

━━ CAMPAIGN ALERTS ━━
🔴 [Client] [Campaign] — budget pacing at 140%, will overspend by EOD
🟡 [Client] [Campaign] — 2 ads disapproved overnight
🟢 All other accounts healthy

━━ URGENT (respond today) ━━
• [sender] in #[channel]: [1-line summary] — [link]
• ...

━━ ACTION NEEDED ━━
• [sender] in #[channel]: [1-line summary] — [link]
• ...

━━ EMAILS NEEDING REPLY ━━
• [sender] — [subject] — [1-line summary]
• ...

━━ TODAY'S CALENDAR ━━
• [time] — [meeting] with [attendees]
• ...

━━ FYI (catch up when free) ━━
• [count] messages in #[channel] — [topic summary]
• ...

━━ STATS ━━
Messages since last digest: [n] (Urgent: [n] | Action: [n] | FYI: [n] | Noise: [n])
Campaign status checks answered by AI yesterday: [n]
```

## Procedure

1. **Campaign alerts**: Run a quick check across all client accounts for pacing issues, disapproved ads, and budget anomalies. Use `campaign-status` skill scripts. This section goes FIRST because it's the most operationally important.
2. **Slack triage**: Read `~/.hermes/state/slack-triage-log.jsonl` for the past 24 hours.
3. **Email**: Read unread emails, classify as needing-reply or informational.
4. **Calendar**: Pull today's meetings if calendar integration is available.
5. Compile and deliver via Slack DM.
6. Write marker to `~/.hermes/state/last-digest-ts.txt`.

## Pitfalls

- Campaign alerts section may be slow if there are many client accounts. Run checks in parallel if possible.
- If the Google Ads API is unreachable, still send the rest of the digest and note "Campaign data unavailable — API error."
