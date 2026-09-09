# Computer-Use Automation System

A small end-to-end system that lets an LLM discover how to accomplish a goal inside a
UI-only ("no API") application, records that run as a reusable, typed capability artifact, and
replays the artifact deterministically without the model in the loop.

Built for the interface.ai take-home assignment. See `REPORT.md` for the design write-up.

> Status: under active development. This section will be filled in with real setup/run
> instructions as each piece lands — see the phase checklist below for what's currently working.

## Setup

_(to be filled in — Python version, `pip install -r requirements.txt`, `playwright install`,
`.env` from `.env.example`, how to start the mock app)_

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

- [ ] Mock target app
- [ ] Surface abstraction (perceive/act)
- [ ] Discovery agent loop (real LLM-driven run)
- [ ] Artifact schema + recorder
- [ ] Deterministic replay engine
- [ ] Guardrails (allowlist, risk classification, redaction)
- [ ] Escalation & handoff
- [ ] Evidence pass (including an error-path replay)
- [ ] REPORT.md write-up
