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

With the mock app running (above) and `ANTHROPIC_API_KEY` set in `.env`:

```
PYTHONPATH=. python -m agent.discovery \
  --goal "Sign on, then look up member 12345 and read their current savings balance" \
  --max-steps 12
```

This runs a real Claude-driven discovery loop against the live mock app and writes evidence
(step-by-step screenshots, a structured decision log, and the run result) to
`evidence/runs/<timestamp>_discovery/`. Uses `claude-sonnet-5` by default; override with the
`ANTHROPIC_MODEL` env var (e.g. `claude-haiku-4-5-20251001` for a cheaper/faster run).

Replay the recorded capability deterministically (no LLM) - note this works for *any* member ID,
not just the one it was recorded on:

```
PYTHONPATH=. python -m replay.engine \
  --artifact artifacts/store/lookup-member-savings-balance.v2.json \
  --param operator_id=tester --param operator_password=x --param member_id=23456
```

Try `member_id=99999` (not-found) or `member_id=90001` (permission-denied) to see the
business-outcome path, or stop the mock app first to see the hard-failure path.

A second, richer capability is also recorded - opening a sub-account (multi-field form ->
confirmation screen), deliberately stopping short of the final irreversible confirmation click:

```
PYTHONPATH=. python -m replay.engine \
  --artifact artifacts/store/open-sub-account.v2.json \
  --param operator_id=tester --param operator_password=x --param member_id=23456 \
  --param account_type="Money Market" --param initial_deposit=250
```

Both capabilities exist as `.v1` (recorded with `claude-haiku-4-5-20251001`) and `.v2`
(recorded with `claude-sonnet-5`) artifacts - a deliberate use of the schema's versioning to
show the same recording pipeline works unchanged across models. `.v2` is current/recommended.

See `evidence/README.md` for an indexed walkthrough of every captured run - discovery, replay
success, two distinct business-outcome classes, and a real escalation/handoff.

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
- [x] Discovery agent loop (real LLM-driven run)
- [x] Artifact schema + recorder
- [x] Deterministic replay engine
- [x] Guardrails (allowlist, risk classification, redaction)
- [x] Escalation & handoff
- [x] Evidence pass (including an error-path replay)
- [ ] REPORT.md write-up
