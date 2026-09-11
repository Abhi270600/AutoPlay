# Computer-Use Automation System

A small end-to-end system that lets an LLM discover how to accomplish a goal inside a
UI-only ("no API") application, records that run as a reusable, typed capability artifact, and
replays the artifact deterministically without the model in the loop.

Built for the interface.ai take-home assignment. See `REPORT.md` for the design write-up.

## Setup

```
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\activate on cmd/PowerShell
pip install -r requirements.txt
playwright install chromium
cp .env.example .env            # then fill in ANTHROPIC_API_KEY
```

`ANTHROPIC_API_KEY` is only needed for discovery (the LLM-driven step). Replay never calls an
LLM at all, so you can skip the `.env` setup entirely and go straight to the replay commands
below if you just want to run the deterministic path against an already-recorded artifact.

Start the mock target app (a fake legacy bank servicing tool the agent will operate):

```
python mock_app/app.py
```

It listens on http://localhost:5000. Any username/password logs in (this is a mock).
Try member IDs `12345` and `23456`; `90001` is a permission-denied case and any other ID is
a not-found case.

## Demo path

With the mock app running (above) and `ANTHROPIC_API_KEY` set in `.env`, run the agent on a goal:

```
PYTHONPATH=. python -m agent.discovery \
  --goal "Sign on, then look up member 12345 and read their current savings balance" \
  --max-steps 12
```

This runs a real Claude-driven discovery loop against the live mock app and writes evidence
(step-by-step screenshots, a structured decision log, and the run result) to
`evidence/runs/<timestamp>_discovery/`. Uses `claude-sonnet-5` by default; override with the
`ANTHROPIC_MODEL` env var (e.g. `claude-haiku-4-5-20251001` for a cheaper/faster run).

There's a second, richer goal recorded too - opening a sub-account (multi-field form ->
confirmation screen), deliberately stopping short of the final irreversible confirmation click:

```
PYTHONPATH=. python -m agent.discovery \
  --goal "Sign on, then open a new Money Market sub-account with an initial deposit of 250 dollars for member 12345, and reach the confirmation screen. Do not click the final confirm button - stop once the confirmation screen is displayed." \
  --max-steps 15
```

Turn a successful run into a saved capability artifact:

```
PYTHONPATH=. python -m artifacts.recorder
```

This reads each discovery log and writes `artifacts/store/*.v1.json`. Note that
`artifacts/recorder.py` currently points at the two specific discovery runs already checked into
`/evidence/runs/` (the exact runs the two commands above originally produced), not simply "the
most recent run" - if you run discovery again yourself and want to record *your* fresh run
instead, update the `discovery_run_dir` path in `artifacts/recorder.py` to point at your new
`evidence/runs/<timestamp>_discovery/` folder first.

Then replay the resulting artifact deterministically (no LLM) - note this works for *any* member
ID, not just the one it was recorded on:

```
PYTHONPATH=. python -m replay.engine \
  --artifact artifacts/store/lookup-member-savings-balance.v1.json \
  --param operator_id=tester --param operator_password=x --param member_id=23456
```

Try `member_id=99999` (not-found) or `member_id=90001` (permission-denied) to see the
business-outcome path, or stop the mock app first to see the hard-failure path.

And the second capability:

```
PYTHONPATH=. python -m replay.engine \
  --artifact artifacts/store/open-sub-account.v1.json \
  --param operator_id=tester --param operator_password=x --param member_id=23456 \
  --param account_type="Money Market" --param initial_deposit=250
```

See `evidence/README.md` for an indexed walkthrough of every captured run - discovery, replay
success, two distinct business-outcome classes, and a real escalation/handoff.

### Optional stretch goal: agent-facing capability interface

Every saved capability, exposed as a tool a calling agent could discover and invoke by name with
typed args (assignment section 8). The replay commands above take a file path (`--artifact
artifacts/store/....json`); this takes a capability name instead, and, more importantly, is also
a plain Python function (`capabilities.interface.invoke()`) that other code can call directly, no
shelling out to a subprocess needed, which is what actually matters for an AI agent calling this.

See the tool catalog every saved capability generates automatically:

```
PYTHONPATH=. python -m capabilities.interface catalog
```

Invoke one by name (writes the same kind of evidence, screenshots and a structured log, as the
replay commands above, to `evidence/runs/<timestamp>_invoke_<name>/`):

```
PYTHONPATH=. python -m capabilities.interface invoke lookup-member-savings-balance \
  --param operator_id=tester --param operator_password=x --param member_id=23456
```

No LLM involved anywhere in either command; both call the same, unmodified `replay.engine.run_replay()`
the CLI commands above already use. See `capabilities/interface.py`.

In everything above, a human still picked the capability name and typed the arguments. This one
proves an actual AI agent can do both from a plain-English request, handing a live Claude call
the real catalog as its tool list and letting it choose and fill in the arguments itself (costs
one real API call):

```
PYTHONPATH=. python scripts/demo_agent_calls_capability.py
```

## Project layout

```
mock_app/       the legacy-style target Flask app (the "surface" being automated)
agent/          perception/action abstraction + Claude-driven discovery loop + guardrails
artifacts/      capability artifact schema + recorder
replay/         deterministic replay engine + outcome classification
escalation/     human-in-the-loop handoff
capabilities/   agent-facing capability interface (optional stretch goal)
evidence/       saved logs/screenshots/artifacts from real runs
config/         allowlist / guardrail policy
tests/          guardrail unit tests + handoff/escalation tests + a Surface smoke test
scripts/        one-off tooling: interactive escalation evidence capture, a discovery-log viewer,
                a real-agent-picks-a-capability demo
```
