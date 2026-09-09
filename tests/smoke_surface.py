"""
Manual smoke test for the Surface abstraction against the running mock app.
Not a pytest suite (that comes later, once the shape has settled) - just
enough to prove get_state()/act() actually work end to end.

Run with the mock app already up on http://localhost:5000:
    python tests/smoke_surface.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

from agent.actions import Action, ElementRef
from agent.surface import Surface

evidence_dir = Path("evidence/smoke")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:5000/login")
    surface = Surface(page)

    state = surface.get_state(evidence_dir, step=0)
    print("STATE 0 url:", state.url)
    assert "login" in state.url
    assert "Operator ID" in state.aria_snapshot, state.aria_snapshot

    r = surface.act(Action(type="type", target=ElementRef(role="textbox", name="Operator ID"), value="tester"))
    assert r.ok, r.error
    r = surface.act(Action(type="click", target=ElementRef(role="button", name="Sign On")))
    assert r.ok, r.error

    state = surface.get_state(evidence_dir, step=1)
    print("STATE 1 url:", state.url)
    assert "search" in state.url

    r = surface.act(Action(type="type", target=ElementRef(role="textbox", name="Member ID / Account Number"), value="12345"))
    assert r.ok, r.error
    r = surface.act(Action(type="click", target=ElementRef(role="button", name="Find Member")))
    assert r.ok, r.error

    state = surface.get_state(evidence_dir, step=2)
    print("STATE 2 url:", state.url)
    assert "/members/12345" in state.url
    assert surface.page_contains_text("Savings Balance")

    r = surface.act(Action(
        type="extract",
        target=ElementRef(role="cell", name="$4231.00", exact=True),
        extract_as="savings_balance",
    ))
    print("extracted:", r.extracted_value)
    assert r.ok and r.extracted_value == "$4231.00", r

    browser.close()

print("SMOKE TEST PASSED")
