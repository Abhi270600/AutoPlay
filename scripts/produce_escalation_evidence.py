"""
Produces the escalation/handoff evidence capture for /evidence/ - with a real
human at the keyboard, not a scripted stand-in.

Loads the real, recorded open-sub-account.v1.json artifact and appends one
extra step: clicking "Confirm and Open Account". The real artifact
deliberately stops one step short of that click, by design, per the
assignment's own goal phrasing, so it never reaches a guardrail-blocked step
on its own. This is the ONLY difference from the real capability - every
other step (sign on, search for the member, open the sub-account form, fill
it out) is the real recorded artifact's own steps, unmodified, not a
hand-typed approximation of them.

Runs the browser headed (visible), so you can watch it happen: automation
drives all the real recorded steps on its own, then pauses at the
guardrail-blocked step and drops you into a real `operator>` prompt in this
terminal. Type:

    click button "Confirm and Open Account"
    resume

...to approve the risky action yourself and complete the run as a success -
that's what evidence/runs/escalation_human_completes_confirmation/ is meant
to capture. You can also type `state` to see the page, `screenshot` to
capture one, or just `resume` on its own to decline and let the run end in
failure instead (also a legitimate, real outcome - see tests/test_handoff.py
scenario 1 for that path already covered as an automated test).

Needs the mock app running on http://localhost:5000, with member 12345 not
already holding a Money Market sub-account (a fresh mock_app/app.py restart
guarantees this, since member data is in-memory only), and needs
artifacts/store/open-sub-account.v1.json to already exist (run
artifacts/recorder.py first if it doesn't).

Run with: PYTHONPATH=. python scripts/produce_escalation_evidence.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

from artifacts.schema import ArtifactStep, CapabilityArtifact, Checkpoint, TargetLocator
from replay.engine import run_replay

base_artifact = CapabilityArtifact.model_validate_json(
    Path("artifacts/store/open-sub-account.v1.json").read_text()
)

risky_step = ArtifactStep(
    index=len(base_artifact.steps) + 1,
    action="click",
    target=TargetLocator(
        role="button", name="Confirm and Open Account",
        reasoning="The one step the real capability deliberately stops short of - added here "
        "only to produce evidence of the guardrail block and human handoff.",
    ),
)

demo_artifact = base_artifact.model_copy(
    update={
        "id": "open-sub-account-and-confirm-demo",
        "description": (
            base_artifact.description
            + " [DEMO VARIANT: appends the final confirmation click that the real capability "
            "deliberately omits, for escalation/handoff evidence purposes only.]"
        ),
        "steps": [*base_artifact.steps, risky_step],
        "checkpoint": Checkpoint(kind="text_present", value="Sub-Account Opened Successfully"),
    }
)

evidence_dir = Path("evidence/runs/escalation_human_completes_confirmation")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    result = run_replay(
        demo_artifact,
        {
            "operator_id": "tester", "operator_password": "x", "member_id": "12345",
            "account_type": "Money Market", "initial_deposit": "300",
        },
        page,
        evidence_dir=evidence_dir,
        # No escalation_commands passed - this defaults to reading real
        # commands from stdin. You are the human in this run.
    )
    browser.close()

evidence_dir.mkdir(parents=True, exist_ok=True)
(evidence_dir / "replay_result.json").write_text(result.model_dump_json(indent=2))
(evidence_dir / "demo_artifact.json").write_text(demo_artifact.model_dump_json(indent=2))
print(result.model_dump_json(indent=2))
print("Escalation evidence written to", evidence_dir)
