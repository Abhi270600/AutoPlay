"""
Proves the discovery loop's guardrail-block -> escalate -> continue wiring
works, without spending real API budget: a fake Anthropic client scripts the
model's turns deterministically (its create() just returns the next
pre-built response), while everything else - the real mock app, real
Playwright Surface, real guardrail check, real escalate() with a scripted
operator command - is exercised for real.

Needs the mock app running on http://localhost:5000.
Run with: python tests/test_discovery_escalation.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

from agent.discovery import run_discovery
from agent.surface import Surface


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, id_, input_):
        self.id = id_
        self.input = input_


class FakeResponse:
    def __init__(self, input_, block_id):
        self.content = [FakeToolUseBlock(block_id, input_)]
        self.stop_reason = "tool_use"


class FakeMessages:
    def __init__(self, script):
        self._script = iter(script)

    def create(self, **kwargs):
        return next(self._script)


class FakeClient:
    def __init__(self, script):
        self.messages = FakeMessages(script)


SCRIPT = [
    FakeResponse({"type": "type", "target": {"role": "textbox", "name": "Operator ID"}, "value": "tester", "reason": "sign on"}, "t1"),
    FakeResponse({"type": "type", "target": {"role": "textbox", "name": "Password"}, "value": "x", "reason": "sign on"}, "t2"),
    FakeResponse({"type": "click", "target": {"role": "button", "name": "Sign On"}, "reason": "sign on"}, "t3"),
    # Member 23456 only has a CD sub-account so far, so opening a Money
    # Market one here won't hit the duplicate-account interstitial.
    FakeResponse({"type": "navigate", "value": "http://localhost:5000/members/23456/sub-accounts/new", "reason": "go to form"}, "t4"),
    FakeResponse({"type": "select", "target": {"role": "combobox", "name": "Account Type"}, "value": "Money Market", "reason": "pick type"}, "t5"),
    FakeResponse({"type": "type", "target": {"role": "textbox", "name": "Initial Deposit"}, "value": "100", "reason": "enter deposit"}, "t6"),
    FakeResponse({"type": "click", "target": {"role": "button", "name": "Continue"}, "reason": "continue"}, "t7"),
    # This one should be guardrail-blocked, escalated, and NOT executed:
    FakeResponse({"type": "click", "target": {"role": "button", "name": "Confirm and Open Account"}, "reason": "confirm"}, "t8"),
    # The loop must survive the escalation and ask the model again:
    FakeResponse({"type": "done", "reason": "stopping after escalation, for this test"}, "t9"),
]

evidence_dir = Path("evidence/_tmp_discovery_escalation_test")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    surface = Surface(page)

    result = run_discovery(
        goal="test",
        start_url="http://localhost:5000/login",
        surface=surface,
        evidence_dir=evidence_dir,
        max_steps=20,
        client=FakeClient(SCRIPT),
        escalation_commands=["resume"],
    )
    browser.close()

print(result.model_dump_json(indent=2))
assert result.status == "success", result  # loop reached the scripted "done" AFTER surviving the block
assert list((evidence_dir / "handoff").glob("intervention_request_step_*.json")), "escalation was never raised"
assert (evidence_dir / "handoff" / "control_state.json").exists(), "control state was never recorded"

print("DISCOVERY ESCALATION TEST PASSED")
