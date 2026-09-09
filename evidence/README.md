# Evidence

Saved artifacts live in `/artifacts/store/`, not duplicated here, to avoid two
copies drifting apart. Everything below is a real run against the live mock
app (`mock_app/`) - nothing here is fabricated or hand-written output.

## Discovery runs (real LLM-driven, `claude-haiku-4-5-20251001`)

- **`20260909_110340_discovery/`** - goal: "Sign on, then look up member 12345
  and read their current savings balance." 10 steps, succeeded. Recorded as
  `artifacts/store/lookup-member-savings-balance.v1.json`.
- **`20260909_163428_discovery/`** - goal: "open a new Money Market sub-account
  ... and reach the confirmation screen. Do not click the final confirm
  button." 15 steps, succeeded, correctly stopped at the confirmation screen
  without attempting the guardrail-classified risky click. Also the first
  live proof that discovery-side redaction works: the log's step 4 shows
  `"value": "[REDACTED]"` for the password field, not the real typed value.
  Recorded as `artifacts/store/open-sub-account.v1.json`.

## Deterministic replay (no LLM)

- **`replay_success_lookup_member/`** - `lookup-member-savings-balance` replayed
  for member **23456** - a *different* member than the one it was recorded
  on (12345). Proves the `next_cell` label-anchored locator genuinely
  generalizes, not just that the recording happens to work for itself.
- **`replay_success_open_subaccount/`** - `open-sub-account` replayed to a
  successful confirmation screen for a fresh member/account-type pair.
- **`replay_error_member_not_found/`** - `open-sub-account` replayed for a
  nonexistent member. `status: business_outcome`, `outcome: member_not_found`
  - a legitimate answer, not a crash.
- **`replay_error_invalid_deposit/`** - `open-sub-account` replayed with a
  negative deposit. `status: business_outcome`, `outcome: invalid_deposit_zero`
  - a different outcome class than not-found, showing the taxonomy isn't a
  single catch-all.

## Escalation & handoff

- **`escalation_human_completes_confirmation/`** - the real, live control
  transfer: automation is blocked at the guardrail-classified "Confirm and
  Open Account" click, raises an intervention request (`handoff/
  intervention_request.json`), and a scripted operator command
  (`click button "Confirm and Open Account"`) completes it on the *same*
  session automation had been driving - not a fresh one. `handoff/
  control_state.json` ends `"control": "automation"`; `handoff/
  handoff_log.jsonl` records exactly what the human did. Uses a small
  hand-built 8-step artifact (`demo_artifact.json`, saved alongside) that
  adds one step to the real recorded flow - the real `open-sub-account.v1`
  capability deliberately stops *before* this click by design, so it never
  reaches a blockable step on its own; this demo artifact exists solely to
  exercise that step for evidence. The replay engine, guardrail policy, and
  escalation code executing it are the same production code paths used
  everywhere else - only this one artifact's steps were hand-built rather
  than freshly discovered, to avoid spending API budget proving discovery
  could reach a state we'd already reached for real in the other run above.

Business-outcome and escalation coverage beyond what's captured here (a
duplicate-account-type outcome, a permission-denied outcome, a human
*declining* the risky action) is exercised in `tests/test_handoff.py` and
`tests/test_guardrails.py` - not duplicated here to keep this folder focused.
