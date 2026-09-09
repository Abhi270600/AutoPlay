# Computer-Use Automation System

A small end-to-end system that lets an LLM discover how to accomplish a goal inside a
UI-only ("no API") application, records that run as a reusable, typed capability artifact, and
replays the artifact deterministically without the model in the loop.

Built for the interface.ai take-home assignment. See `REPORT.md` for the design write-up.

> Status: under active development. This section will be filled in with real setup/run
> instructions as each piece lands — see the phase checklist below for what's currently working.

## Setup

```
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\activate on cmd/PowerShell
pip install -r requirements.txt
playwright install chromium
cp .env.example .env            # then fill in ANTHROPIC_API_KEY
```

Start the mock target app (a fake legacy bank servicing tool the agent will operate):

```
python mock_app/app.py
```

It listens on http://localhost:5000. Any username/password logs in (this is a mock).
Try member IDs `12345` and `23456`; `90001` is a permission-denied case and any other ID is
a not-found case.

## Demo path

_(to be filled in — exact commands: run discovery on a goal, then replay the resulting artifact)_

## Project layout

```
mock_app/     the legacy-style target Flask app (the "surface" being automated)
agent/        perception/action abstraction + Claude-driven discovery loop + guardrails
artifacts/    capability artifact schema + recorder
replay/       deterministic replay engine + outcome classification
escalation/   human-in-the-loop handoff
evidence/     saved logs/screenshots/artifacts from real runs
config/       allowlist / guardrail policy
```

## Phase checklist

- [x] Mock target app
- [x] Surface abstraction (perceive/act)
- [ ] Discovery agent loop (real LLM-driven run)
- [ ] Artifact schema + recorder
- [ ] Deterministic replay engine
- [ ] Guardrails (allowlist, risk classification, redaction)
- [ ] Escalation & handoff
- [ ] Evidence pass (including an error-path replay)
- [ ] REPORT.md write-up
