# Contributing to Zen Den

Thank you for your interest in making Zen Den better! Whether you're fixing a bug, adding a feature, or improving documentation, your contribution is welcome and appreciated.

## Getting Started

### 1. Fork & Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/<your-username>/zen-den.git
cd zen-den
```

### 2. Set Up the Dev Environment

Zen Den requires **Python 3.10+**.

```bash
python3 -m venv venv
source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

### 3. Run Locally

```bash
python3 demo/desktop.py
```

The app window will launch automatically. You can now make changes and restart the app to see them.

## Project Structure

```
zen-den/
├── demo/
│   ├── desktop.py          # Main entry point (pywebview app)
│   ├── index.html          # Primary UI
│   ├── api.py              # Python ↔ JS bridge
│   ├── slack_responder.py  # Slack auto-responder logic
│   ├── email_watcher.py    # IMAP email watcher
│   ├── report_builder.py   # PDF report generation
│   └── assets/             # Images, icons, styles
├── requirements.txt
├── LICENSE
├── README.md
└── CONTRIBUTING.md
```

## How to Submit a Pull Request

1. **Fork** the repository on GitHub.
2. **Create a branch** from `main` for your change:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** — keep commits focused and descriptive.
4. **Test** your changes by running the app locally (`python3 demo/desktop.py`).
5. **Push** your branch and open a **Pull Request** against `main`.

Please include a clear description of what your PR does and why. If it addresses an open issue, reference it with `Closes #123`.

## Code Style

- **Python** — Follow [PEP 8](https://peps.python.org/pep-0008/). Use meaningful variable names. Keep functions focused and short.
- **JavaScript / HTML / CSS** — Follow the existing patterns in the codebase. Prefer clarity over cleverness.
- No linter is enforced yet, but please keep your code clean and consistent with the surrounding style.

## Reporting Issues

A good issue includes:

- **A clear title** that summarizes the problem or request.
- **Steps to reproduce** (for bugs) — what you did, what you expected, what actually happened.
- **Environment details** — OS, Python version, relevant config.
- **Screenshots or logs** if applicable.

If you're unsure whether something is a bug, open the issue anyway — we'd rather hear about it.

## Feature Requests

Feature ideas are welcome! When proposing a new feature:

- Explain the **use case** — what problem does it solve for paid search professionals?
- Describe the **expected behavior** as concretely as you can.
- Note whether you'd be willing to implement it yourself.

## Code of Conduct

Be kind. Be constructive. We're all here to build something that helps marketers breathe easier. Harassment, dismissiveness, and unconstructive negativity have no place in this project. Treat every contributor — beginner or veteran — with respect.

---

Built by [Kalina Lux](https://github.com/KalinaLux)
