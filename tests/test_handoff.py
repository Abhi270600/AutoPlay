"""
Proves the escalation/handoff mechanism is real: a scripted list of commands
stands in for a human typing into the operator prompt, executed against the
SAME live session the automation was using (not a fresh one). Two scenarios:

1. The human declines the risky action (just resumes) -> the capability
   correctly fails its checkpoint, since the sub-account was never created.
2. The human performs the risky action themselves via the operator surface
   -> the capability succeeds, because the human's action on the SAME
   session is what completed it.

Needs the mock app running on http://localhost:5000.
Run with: python tests/test_handoff.py
"""

from playwright.sync_api import sync_playwright

from artifacts.schema import (
    ArtifactStep, CapabilityArtifact, Checkpoint, ParamSpec, Provenance, TargetLocator, TargetSpec,
)
from replay.engine import run_replay


def make_artifact(member_id: str) -> CapabilityArtifact:
    return CapabilityArtifact(
        id="test-handoff",
        version=1,
        description="Synthetic artifact for testing escalation/handoff.",
        target=TargetSpec(base_url="http://localhost:5000", entry_point="/login"),
        provenance=Provenance(discovery_run_id="n/a", model="n/a", recorded_at="n/a"),
        input_params=[
            ParamSpec(name="operator_id", type="string", description="x"),
            ParamSpec(name="operator_password", type="string", description="x"),
        ],
        steps=[
            ArtifactStep(index=1, action="type", value="{{operator_id}}",
                         target=TargetLocator(role="textbox", name="Operator ID", reasoning="x")),
            ArtifactStep(index=2, action="type", value="{{operator_password}}",
                         target=TargetLocator(role="textbox", name="Password", reasoning="x")),
            ArtifactStep(index=3, action="click",
                         target=TargetLocator(role="button", name="Sign On", reasoning="x")),
            ArtifactStep(index=4, action="navigate",
                         value=f"http://localhost:5000/members/{member_id}/sub-accounts/new"),
            ArtifactStep(index=5, action="select", value="Money Market",
                         target=TargetLocator(role="combobox", name="Account Type", reasoning="x")),
            ArtifactStep(index=6, action="type", value="100",
                         target=TargetLocator(role="textbox", name="Initial Deposit", reasoning="x")),
            ArtifactStep(index=7, action="click",
                         target=TargetLocator(role="button", name="Continue", reasoning="x")),
            ArtifactStep(index=8, action="click",
                         target=TargetLocator(role="button", name="Confirm and Open Account", reasoning="x")),
        ],
        outputs=[],
        checkpoint=Checkpoint(kind="text_present", value="Sub-Account Opened Successfully"),
    )


def run(member_id: str, commands: list[str]):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        result = run_replay(
            make_artifact(member_id), {"operator_id": "tester", "operator_password": "x"}, page,
            escalation_commands=iter(commands),
        )
        browser.close()
    return result


print("=== Scenario 1: human declines (just resumes) ===")
# Member 23456 already has a CD sub-account, but declining means nothing is
# created either way - any existing member works, and nothing here mutates
# state, so this scenario is safe to re-run.
result = run("23456", ["resume"])
print(result.model_dump_json(indent=2))
assert result.status == "failure", result  # checkpoint never met - account not created
assert "checkpoint" in result.error.action, result

print("\n=== Scenario 2: human performs the risky action themselves ===")
# Member 12345 has no sub-accounts yet, so the first run creates one for
# real. Re-running this script without restarting the mock app will hit the
# duplicate-account interstitial instead (a different, also-real outcome,
# just not the one this scenario is checking for) - restart mock_app/app.py
# between repeated runs of this specific test.
result = run("12345", ['click button "Confirm and Open Account"', "resume"])
print(result.model_dump_json(indent=2))
assert result.status == "success", result

print("\nHANDOFF TESTS PASSED")
