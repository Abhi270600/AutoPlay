"""
Proves the guardrail block is real at the run_replay() level, not just in the
isolated check_* unit tests - a synthetic artifact walks up to the real
"Confirm and Open Account" button (the actual irreversible action in the mock
app's sub-account flow) and the engine must refuse to click it.

Needs the mock app running on http://localhost:5000.
Run with: python tests/test_guardrails_live.py
"""

from playwright.sync_api import sync_playwright

from artifacts.schema import (
    ArtifactStep, CapabilityArtifact, Checkpoint, ParamSpec, Provenance, TargetLocator, TargetSpec,
)
from replay.engine import run_replay

artifact = CapabilityArtifact(
    id="test-risky-block",
    version=1,
    description="Synthetic artifact for testing the guardrail block on a risky target.",
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
        ArtifactStep(index=4, action="navigate", value="http://localhost:5000/members/12345/sub-accounts/new"),
        ArtifactStep(index=5, action="select", value="Money Market",
                     target=TargetLocator(role="combobox", name="Account Type", reasoning="x")),
        ArtifactStep(index=6, action="type", value="100",
                     target=TargetLocator(role="textbox", name="Initial Deposit", reasoning="x")),
        ArtifactStep(index=7, action="click",
                     target=TargetLocator(role="button", name="Continue", reasoning="x")),
        # The irreversible step - guardrails must block this one:
        ArtifactStep(index=8, action="click",
                     target=TargetLocator(role="button", name="Confirm and Open Account", reasoning="x")),
    ],
    outputs=[],
    checkpoint=Checkpoint(kind="text_present", value="Sub-Account Opened Successfully"),
)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    result = run_replay(
        artifact, {"operator_id": "tester", "operator_password": "x"}, page,
    )
    browser.close()

print(result.model_dump_json(indent=2))
assert result.status == "blocked", result
assert result.guardrail_violation["reason"] == "risky_action_blocked", result

print("LIVE GUARDRAIL BLOCK TEST PASSED - steps 1-7 executed, step 8 was refused")
