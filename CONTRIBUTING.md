# Contributing to Pump Screener Light

Thanks for your interest in contributing! This project is open to bug reports, feature requests, documentation improvements, and code contributions.

## Development Setup

**Prerequisites:** Python 3.10+, Git

```bash
git clone https://github.com/foxclerec/bybit-pump-screener-light.git
cd bybit-pump-screener-light

pip install -r requirements.txt
pip install -r requirements-dev.txt  # pytest, playwright, etc.

# Create .env
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" > .env

# Initialize the database
flask --app app:create_app init-db

# Run the screener (background process)
flask --app app:create_app screener-run

# Run the web server (separate terminal)
flask --app app:create_app run
```

Open `http://127.0.0.1:5000` in your browser.

## Branch & PR Workflow

We use a **single-branch** workflow — all work targets `main`.

1. **Fork** the repo and create a feature branch from `main`
2. Name your branch descriptively: `fix/dedup-race`, `feat/binance-adapter`, `docs/api-examples`
3. Open a PR **into `main`**
4. PRs are **squash-merged** — your commits will become one clean commit on `main`

Releases are cut from `main` via git tags (`v1.0.0`, `v1.1.0`, etc.).

## Pull Request Guidelines

1. **One PR = one change** — keep it focused
2. **Commit messages** — use prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
3. **Code language** — all code, comments, logs, and docstrings must be in English
4. **No new dependencies** without discussion in an issue first
5. Run `pytest` before submitting if tests exist for the area you changed

## Bug Reports

[Open a bug report](https://github.com/foxclerec/bybit-pump-screener-light/issues/new?template=bug_report.md) and include:

- OS and app version (shown in Settings > About)
- Steps to reproduce
- Expected vs actual behavior
- Screenshot or log output if applicable

## Feature Requests

[Open a feature request](https://github.com/foxclerec/bybit-pump-screener-light/issues/new?template=feature_request.md) describing what you'd like and why it would be useful.

## Code Style

- **Python:** PEP 8, type hints on public functions, no `os.path` (use `pathlib`)
- **JavaScript:** vanilla ES6+, no frameworks, no jQuery
- **CSS:** design tokens via CSS custom properties, no inline styles, no Tailwind
- **HTML:** Jinja2 templates, semantic markup

## Architecture Overview

The app has two processes sharing a SQLite database:

- **Screener** (`app/screener/runner.py`) — background process that monitors Bybit and writes signals to the DB
- **Web server** (`app/blueprints/`) — Flask app that serves the UI and reads signals from the DB

See `CLAUDE.md` for detailed architecture documentation.
