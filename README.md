# 🧘 Zen Den

**Breathe easy. It's handled.**

AI-powered marketing automation for paid search professionals.

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Built with Love](https://img.shields.io/badge/Built%20with-%F0%9F%92%9C-blueviolet.svg)](#built-by)

---

## What It Does

- 💬 **Slack auto-responder** — watches channels and answers campaign questions automatically
- ✉️ **Email auto-responder** — IMAP watcher that auto-drafts replies (Gmail, Outlook, Yahoo, any provider)
- 📊 **Campaign dashboard** — live campaign data from Google Ads, Meta, Microsoft, and TikTok at a glance
- 👥 **Client manager** — add, edit, and organize clients and campaigns through the UI
- 📈 **Budget pacing** — visual spend tracking vs. calendar pace
- 🚨 **Anomaly detection** — proactive alerts for ROAS drops, CPC spikes, disapproved promos
- 📄 **One-click PDF reports** — professional client decks with scheduled email delivery
- 📋 **Meeting prep briefs** — one-click client meeting preparation
- ⚡ **36 quick-reply templates** — stop typing the same responses
- ❓ **48 pre-loaded Q&As** — expandable knowledge base
- 🛡️ **Privacy-first** — runs 100% locally, data never leaves your machine
- ⏱️ **Time-saved tracker** — see how many hours the tool is saving you
- 🌐 **Multi-language** — English, Spanish, French, Portuguese
- 🎨 **Beautiful dark/light UI** with calming color psychology

## Video Tour

[**Watch the 2-minute video tour**](https://app.heygen.com/videos/801c0e2ac4dd4f20b456c68bf661fb5a) — see everything Zen Den can do before you install.

## Screenshots

> Screenshots coming soon.

## Quick Start

```bash
git clone https://github.com/KalinaLux/zen-den.git
cd zen-den
pip install -r requirements.txt
python3 demo/desktop.py
```

The Zen Den window will appear — you're ready to go.

## macOS App

Pre-built installers are available on the [Releases](https://github.com/KalinaLux/zen-den/releases) page.

**macOS:** Download the `.dmg`, drag **Zen Den** to Applications, double-click to launch.

**Windows:** Download the `.zip`, extract, and run `Zen Den.exe`.

Both are built automatically via GitHub Actions on every tagged release.

## Requirements

- **Python 3.10+**
- pip packages:

  | Package | Purpose |
  |---------|---------|
  | `pywebview` | Native desktop window |
  | `reportlab` | PDF report generation |
  | `slack-bolt` | Slack app framework |
  | `slack-sdk` | Slack API client |
  | `Pillow` | Image processing |

Install everything at once:

```bash
pip install -r requirements.txt
```

## Project Structure

```
zen-den/
├── demo/
│   ├── desktop.py            # App entry point + HTTP server
│   ├── index.html            # Single-page UI
│   ├── report_generator.py   # PDF report generation
│   ├── report_mailer.py      # Scheduled email delivery
│   ├── google_ads_client.py  # Google Ads API client
│   ├── meta_ads_client.py    # Meta (Facebook) Ads API client
│   ├── microsoft_ads_client.py # Microsoft (Bing) Ads API client
│   ├── tiktok_ads_client.py  # TikTok Ads API client
│   ├── slack_bot.py          # Slack auto-responder
│   ├── email_watcher.py      # IMAP email watcher
│   ├── analytics.py          # Pacing, anomalies, meeting prep
│   ├── i18n.json             # Translations (EN/ES/FR/PT)
│   ├── quick_replies.json    # Pre-built quick reply templates
│   └── mock_campaigns.json   # Demo data
├── config/                   # FAQ, access control, VIP senders
├── build/                    # App icon + DMG assets
├── .github/workflows/        # CI/CD for macOS + Windows builds
├── zenapp.spec               # PyInstaller build spec
├── requirements.txt
├── LICENSE
├── README.md
└── CONTRIBUTING.md
```

## Configuration

All integrations are configured through the **in-app Settings page** — no manual file editing required.

### Slack

Connect your Slack workspace by providing a Bot Token and optionally an App Token for socket mode. Choose which channels Zen Den monitors and customize the AI persona.

### Email

Add any IMAP-compatible email account (Gmail, Outlook, Yahoo, etc.). Zen Den watches your inbox and auto-drafts replies to common campaign questions. You review and send — nothing goes out without your approval.

### Google Ads

Link your Google Ads account via OAuth to pull live campaign data into the dashboard. Zen Den uses read-only access for metrics, pacing, and anomaly detection.

### Meta Ads / Microsoft Ads / TikTok Ads

Same story — connect via OAuth in Settings. Each platform gets its own configuration card. All campaign data is normalized into one unified dashboard.

## Privacy & Security

Zen Den is designed to keep your data under your control:

- **Runs 100% locally** — no cloud backend, no telemetry, no tracking.
- **AI sees questions, not data** — when AI is used, only the question text is sent; raw campaign data stays on your machine.
- **API data is not used for model training** — OpenAI API calls are not used to train models.
- **Full audit trail** — every auto-drafted response is logged so you can review exactly what was sent and when.

## Contributing

Contributions are welcome! Check out the [Contributing Guide](CONTRIBUTING.md) for details on how to get started.

Bug reports, feature requests, and pull requests are all appreciated.

## License

This project is licensed under the [MIT License](LICENSE).

## Built By

Built with 💜 by [Kalina Lux](https://github.com/KalinaLux)

If this tool helps you breathe easier at work, star the repo and share it with a fellow marketer.
