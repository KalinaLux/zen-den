---
name: email-draft-responder
description: Draft context-aware email replies for review, tuned for agency client communication
version: 1.0.0
author: marketing-autopilot
license: MIT
metadata:
  hermes:
    tags: [Productivity, Email, Paid Search, Agency]
    requires_tools: [bash]
    related_skills: [campaign-status]
---

# Email Draft Responder

Read incoming emails and draft replies for the user to review and send. Tuned for agency client communication style.

## When to Use

Triggered on new emails or when user says "draft a reply to [email]."

## Procedure

1. Read the full email: content, sender, subject, thread history.
2. Determine if a reply is needed:
   - Client emails → YES (always)
   - Internal team questions → YES
   - Vendor/platform notifications → Usually NO
   - Newsletters/spam → NO
3. Draft a response considering:
   - **Agency tone**: Professional, confident, proactive. Not overly formal.
   - **Thread context**: What was discussed before
   - **Cross-reference Slack**: If the email topic was discussed in Slack, incorporate that context
   - If email asks about campaign status: pull live data from Google Ads API before drafting (use `campaign-status` skill)
4. Save as draft in email client. Notify user via Slack DM:
   ```
   ✉️ Draft ready — Re: [subject]
   From: [sender]
   Preview: [first 100 chars]
   ⚠️ Contains campaign data — please verify before sending
   → Reply "send" to send as-is, or review in Gmail
   ```

## Safety

- NEVER auto-send. All drafts require user approval.
- If draft contains campaign performance numbers, flag with ⚠️ — user must verify accuracy.
- Flag anything with contract, legal, or billing language.
- Insert `[CONFIRM: ...]` placeholders for any specific numbers or dates you're unsure about.

## Agency-Specific Style

- Use "we" not "I" when speaking about the team's work
- Be proactive: don't just answer the question, suggest next steps
- For client performance questions: lead with the insight, then the data
- Close with clear next steps and timeline
