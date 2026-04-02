---
name: promo-checker
description: Check if promotions, extensions, and sale adjustments are active on campaigns
version: 1.0.0
author: marketing-autopilot
license: MIT
metadata:
  hermes:
    tags: [Paid Search, Google Ads, Promotions, Agency]
    requires_tools: [bash]
    related_skills: [campaign-status]
required_environment_variables:
  - name: GOOGLE_ADS_DEVELOPER_TOKEN
    prompt: "Enter your Google Ads API developer token"
    required_for: "Google Ads API access"
---

# Promo Checker

Check if promotions, sale extensions, ad customizers, and promotional adjustments have been applied to campaigns.

## When to Use

Activate when someone asks:
- "Has the promo been applied to [campaign]?"
- "Is the [sale/discount/coupon] active?"
- "Did we add the promotion extension to [client]?"
- "Are the sale sitelinks live?"
- "What promos are running for [client]?"
- "Did we update the ad copy with the discount?"
- "Is the seasonal adjustment active?"

## Quick Reference

| Command | What it does |
|---------|-------------|
| `python3 scripts/check_promos.py --client "Nike" --campaign "Q2 Sale"` | Check promos on a specific campaign |
| `python3 scripts/check_promos.py --client "Nike" --list-all` | List all active promos/extensions for a client |
| `python3 scripts/check_promos.py --client "Nike" --type promotion_extension` | Check a specific promo type |

## Procedure

1. **Parse the question** to extract:
   - **Client name**
   - **Campaign name** (if specific)
   - **Promo type**: promotion extension, sale sitelink, ad customizer, bid adjustment, or general

2. **Check access control** — same as campaign-status skill. Verify authorization.

3. **Run the lookup script**:
   ```bash
   python3 scripts/check_promos.py --client "<client>" --campaign "<campaign>"
   ```

4. **Read the output** and check for:
   - **Promotion extensions**: Are they approved and serving? What's the promo text, discount, and date range?
   - **Sitelinks**: Are sale-specific sitelinks active?
   - **Ad copy**: Do current ads contain promo language (% off, sale, discount, code)?
   - **Bid adjustments**: Are there seasonal bid adjustments or audience adjustments tied to the promo?
   - **Scheduled campaigns**: Is there a promo-specific campaign, and is it enabled/scheduled?

5. **Format response**. Examples:
   - "Yes, the 20% off promotion extension is active on Nike Q2 Sale. It shows 'Save 20% — Use code SUMMER20' and runs through June 30."
   - "The promo extension is approved but the campaign it's on (Nike Spring Sale) is currently PAUSED. The extension will go live once the campaign is enabled."
   - "I see 2 promotion extensions for Acme Corp — one is active (15% off sitewide), one is scheduled to start May 1 (Memorial Day sale)."

6. **Log the query** to audit log.

## Pitfalls

- **Promo applied ≠ promo serving**: An extension can be added to a campaign but not serving (campaign paused, extension disapproved, schedule not started). Always check both.
- **Multiple promo types**: A "promo" could mean an extension, a sitelink, ad copy, or a bid adjustment. When ambiguous, check all of them and report what you find.
- **Disapproved extensions**: If a promotion extension is disapproved by Google, flag this prominently — the team needs to fix it.

## Verification

The response should match what's visible in Google Ads UI under Extensions > Promotion, and in the campaign's ad copy.
