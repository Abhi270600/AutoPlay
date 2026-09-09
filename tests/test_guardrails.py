"""
Guardrail policy is pure logic - no browser needed to verify it, unlike the
Surface/discovery/replay pieces. Run with: python tests/test_guardrails.py
"""

from agent.actions import Action, ElementRef
from agent.guardrails import GuardrailPolicy, check_discovery_action, check_replay_step
from artifacts.schema import ArtifactStep, TargetLocator

policy = GuardrailPolicy.load()

# --- allowlist: routes ------------------------------------------------------

assert policy.is_url_allowed("http://localhost:5000/members/12345")
assert policy.is_url_allowed("http://localhost:5000/members/12345/sub-accounts/new")
assert policy.is_url_allowed("http://localhost:5000/login")
assert not policy.is_url_allowed("http://evil.example.com/members/12345")
assert not policy.is_url_allowed("http://localhost:5000/admin")

# --- allowlist: action types -------------------------------------------------

assert policy.is_action_type_allowed("click")
assert not policy.is_action_type_allowed("drag_and_drop")

# --- risk classification -----------------------------------------------------

assert policy.is_risky_target("button", "Confirm and Open Account")
assert not policy.is_risky_target("button", "Find Member")

# --- redaction ---------------------------------------------------------------

password_action = Action(
    type="type", target=ElementRef(role="textbox", name="Password"), value="password123",
)
redacted = policy.redact_action(password_action)
assert redacted["value"] == "[REDACTED]", redacted

member_id_action = Action(
    type="type", target=ElementRef(role="textbox", name="Member ID / Account Number"), value="12345",
)
not_redacted = policy.redact_action(member_id_action)
assert not_redacted["value"] == "12345", not_redacted

# --- discovery-side check_action ---------------------------------------------

risky_click = Action(type="click", target=ElementRef(role="button", name="Confirm and Open Account"))
violation = check_discovery_action(policy, risky_click, current_url="http://localhost:5000/members/12345")
assert violation is not None and violation.reason == "risky_action_blocked", violation

safe_click = Action(type="click", target=ElementRef(role="button", name="Find Member"))
assert check_discovery_action(policy, safe_click, current_url="http://localhost:5000/members/search") is None

out_of_scope_nav = Action(type="navigate", value="http://evil.example.com/steal")
violation = check_discovery_action(policy, out_of_scope_nav, current_url="http://localhost:5000/login")
assert violation is not None and violation.reason == "url_not_allowed", violation

# --- replay-side check_replay_step --------------------------------------------

risky_step = ArtifactStep(
    index=1, action="click",
    target=TargetLocator(role="button", name="Confirm and Open Account", reasoning="test"),
)
violation = check_replay_step(policy, risky_step, current_url="http://localhost:5000/members/12345/sub-accounts/new")
assert violation is not None and violation.reason == "risky_action_blocked", violation

safe_step = ArtifactStep(
    index=1, action="extract",
    target=TargetLocator(role="cell", name="Savings Balance:", exact=True, relative="next_cell", reasoning="test"),
)
assert check_replay_step(policy, safe_step, current_url="http://localhost:5000/members/12345") is None

print("ALL GUARDRAIL TESTS PASSED")
