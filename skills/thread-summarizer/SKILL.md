---
name: thread-summarizer
description: Summarize long Slack threads into bullet points with decisions and action items
version: 1.0.0
author: marketing-autopilot
license: MIT
metadata:
  hermes:
    tags: [Productivity, Slack, Summarization]
    requires_tools: [bash]
---

# Thread Summarizer

Condense long Slack threads into a scannable summary.

## When to Use

Triggered when the user says "summarize this thread", "tldr", "what happened in this thread", or "catch me up on #channel."

## Output Format

```
📝 Thread Summary — #[channel] ([N] messages, [timespan])

DECISIONS:
• [Decision + who made it]

ACTION ITEMS:
• [Person]: [Task] (by [deadline if mentioned])

KEY POINTS:
• [Topic — who raised it]

UNRESOLVED:
• [Open questions]
```

## Procedure

1. Fetch all messages in the thread.
2. Extract decisions, action items (attributed to specific people), key discussion points, and unresolved items.
3. Keep under 300 words. Prioritize decisions and action items.
4. For paid-search-specific threads: highlight any campaign changes decided, budget adjustments, or client feedback.
5. Post summary as a reply in the thread.

## Pitfalls

- Threads under 5 messages: say "Thread is short enough to read directly."
- Preserve all deadlines and dates.
- If campaign-specific decisions were made, format them clearly: "Decided to pause Nike Brand campaign until May 1."
