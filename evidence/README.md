# Evidence

`artifacts/` holds copies of the two capability artifacts, for convenience. `/artifacts/store/`
remains the source of truth the system actually reads from and writes to; these are copies so
the artifacts are visible right here alongside the runs that produced and used them, not
scattered across the repo.

Everything below is a real run against the live mock app (`mock_app/`). Nothing here is
fabricated or hand-written output.

## Discovery runs (real LLM-driven, `claude-sonnet-5`)

- **`20260910_222431_discovery/`** - goal: "Sign on, then look up member 12345 and read their
  current savings balance." Completed in 7 steps. Recorded as
  `lookup-member-savings-balance.v1.json`.
- **`20260910_222734_discovery/`** - goal: "open a new Money Market sub-account ... and reach
  the confirmation screen. Do not click the final confirm button." Completed in 10 steps,
  correctly stopped at the confirmation screen without attempting the guardrail-classified risky
  click, unprompted by any escalation. Recorded as `open-sub-account.v1.json`.
- The first run's log (`20260910_222431_discovery/discovery_log.jsonl`, step 2) is the live
  proof that discovery-side redaction works: the field shows `"value": "[REDACTED]"` for the
  password, not the real typed value.
- **`20260911_102111_discovery/`** - goal: same sub-account flow, but this time explicitly told
  to *complete* the process, "including confirming and finalizing the new account", instead of
  stopping short. Live proof that the discovery-side guardrail block holds under a real model
  actually trying the blocked action, not just a unit test of the check function. Claude
  attempted the "Confirm and Open Account" click at step 10, got blocked, was handed back
  control after declining, **tried the identical click again at step 11**, got blocked a second
  time, and only then gave up with a clear `fail` explaining exactly why ("blocked by a
  guardrail policy... cannot bypass this block"). `handoff/handoff_log.jsonl` shows both
  escalations distinctly (`intervention_request_step_010.json` and `..._011.json`) - catching a
  real bug along the way: the handoff log originally overwrote itself on a second escalation
  within the same run, losing the first one's entries. Fixed in `escalation/handoff.py` (append,
  not overwrite; per-step request filenames) and this run re-captured to prove the fix.

## Deterministic replay (no LLM)

- **`replay_success_lookup_member/`** - `lookup-member-savings-balance.v1` replayed for member
  **23456**, a *different* member than the one it was recorded on (12345). Returns their real
  balance ($1500.50). Proves the `next_cell` label-anchored locator genuinely generalizes, not
  just that the recording happens to work for itself.
- **`replay_success_open_subaccount/`** - `open-sub-account.v1` replayed to a successful
  confirmation screen for a fresh member/account-type pair.
- **`replay_error_member_not_found/`** - `open-sub-account.v1` replayed for a nonexistent
  member. `status: business_outcome`, `outcome: member_not_found`, a legitimate answer, not a
  crash.
- **`replay_error_invalid_deposit/`** - `open-sub-account.v1` replayed with a negative deposit.
  `status: business_outcome`, `outcome: invalid_deposit_zero`, a different outcome class than
  not-found, showing the taxonomy isn't a single catch-all.

## Escalation & handoff

- **`escalation_human_completes_confirmation/`** - the real, live control transfer, with an
  actual human at the keyboard, not a scripted stand-in. Uses `demo_artifact.json`: the real
  recorded `open-sub-account.v1` steps (sign on, search for the member, open the sub-account
  form, fill it out, all 9 of them, unmodified) plus one appended step clicking "Confirm and
  Open Account", the one action the real capability deliberately never includes.
  - Automation drives all 9 real steps on its own (`step_001.png` through `step_009.png`).
  - Step 10 is refused by the guardrail (`handoff/intervention_request.json`), which raises an
    intervention request and pauses automation.
  - A human takes over the *same* live session (`handoff/control_state.json` flips to
    `"control": "human"`) and, through the real typed operator prompt (not by clicking directly
    in the browser), issues `click button "Confirm and Open Account"` themselves.
    `handoff/handoff_log.jsonl` records that exact command and that it succeeded.
  - The human types `resume`; control flips back (`control_state.json` ends
    `"control": "automation"`), and the run completes with `status: success`
    (`success_final.png`, `replay_result.json`).
  - This is the strongest evidence in the whole project that the handoff is real: the account
    was genuinely created, by a human, on the exact session automation had already been driving,
    not a fresh one.

Business-outcome and escalation coverage beyond what's captured here (a duplicate-account-type
outcome, a permission-denied outcome, a human *declining* the risky action) is exercised in
`tests/test_handoff.py` and `tests/test_guardrails.py`, not duplicated here to keep this folder
focused.

## Optional stretch goal: agent-facing capability interface

One engine (`run_replay()`), two doors into it: `replay.engine`'s own CLI by file path (see
above), and `capabilities.interface` by name (`invoke()`, or its own CLI:
`python -m capabilities.interface catalog` / `invoke <name> --param ...`, not separately
captured here, `catalog` is a pure read of `artifacts/store/` and `invoke` produces the same
evidence shape as any other replay run). The entry below isn't a third door; it's a different
*caller* using door two, a real AI instead of a human typing the name and arguments.

- **`20260911_120853_agent_call/`** - a real Claude call, handed the exact catalog
  `build_catalog()` produces as its actual `tools=[...]` list (the same forced tool-calling
  pattern `agent/discovery.py` already uses, just choosing between whole capabilities instead of
  individual clicks), given a plain-English request: *"Check the savings balance of member
  12345. Sign on as user_test and password as xxxxx."* `agent_decision.json` shows exactly what
  it chose: the capability `lookup-member-savings-balance`, and arguments
  (`operator_id: "user_test"`, `operator_password: "xxxxx"`, `member_id: "12345"`) pulled
  correctly out of the sentence, values that don't even match the default example this script
  ships with, proving it's genuinely reasoning over the request, not pattern-matching a fixed
  phrase. `invoke_result.json` shows the real result, `status: success`,
  `savings_balance: "$4231.00"`, and the per-step screenshots plus `replay_log.jsonl` are the
  same real replay evidence every other run in this folder has, since `invoke()` was called with
  a real `evidence_dir` this time. `scripts/demo_agent_calls_capability.py` is the one script in
  this project that costs real API money purely to prove an *agent*, not a human, can discover
  and correctly call a saved capability - everything else demonstrating this interface is
  deliberately free.
