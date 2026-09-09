"""
The discovery agent loop: observe -> decide -> act, driven by Claude, against
a live Surface. This is the one part of the system that is non-deterministic
and model-driven - everything downstream (the artifact, replay) exists so
this loop only has to run once per capability.

Design choice worth defending: the model's decision is forced through a single
tool ("act") whose input schema mirrors agent.actions.Action exactly. We never
ask the model for free-text JSON and parse it ourselves - tool_choice forces a
schema-validated action every turn, so "the model decided something we can't
parse" is not a failure mode we have to handle.
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from anthropic import Anthropic, BadRequestError
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

from agent.actions import Action, ElementRef
from agent.guardrails import GuardrailPolicy, check_discovery_action
from agent.surface import Surface

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

SYSTEM_PROMPT = """\
You are an automation agent operating a legacy bank member-servicing web
application through its accessibility tree. You do not see pixels; you see
a textual ARIA snapshot of the current page (its accessible roles and names),
plus the URL and title. This app has no test IDs and a messy, table-based
DOM, so the accessibility tree is your only reliable signal.

You are given a GOAL. On each turn, decide exactly one next action by calling
the `act` tool. Available action types:
- navigate: go to a URL (set `value`).
- click: click an element (set `target`).
- type: fill a text field (set `target` and `value`).
- select: choose an option in a dropdown (set `target` and `value`, the
  option's visible label).
- extract: read the text of an element as an output (set `target` and
  `extract_as`, a short key name for this piece of data).
- wait: pause briefly before re-observing (set `value` to milliseconds).
- done: the goal has been fully achieved. Call this once all needed data has
  been extracted and/or the target state has been reached.
- fail: the goal cannot be achieved (e.g. a permission or not-found error
  blocks progress). Set `reason` to explain why, plainly.

For `target`, set `role` and `name` to match an element in the ARIA snapshot
as closely as possible. Name matching is substring-based by default; set
`exact: true` on the target if you need to match one specific element among
several whose names overlap (e.g. a table cell nested inside a larger cell
that contains the same text).

You may only operate within http://localhost:5000 - do not navigate anywhere
else. Always include a brief `reason` for your action.

You will land on a sign-on screen first. This is a mock system: any Operator
ID and Password will authenticate successfully, so use any values to sign on
before pursuing the goal.

Known quirk of this app: it uses nested tables for layout, so a large outer
cell's accessible name can contain a smaller inner cell's text as a substring
(e.g. an outer cell spanning a whole record also "contains" a dollar amount
that actually lives in one specific inner cell). When you `extract`, always
set `exact: true` and match the value's exact visible text, so you target the
innermost element containing precisely that string rather than a large
ancestor. A future automated replay of your actions will have no model to
interpret a noisy extracted value, so the extracted text must be exactly the
data point requested - nothing more.
"""

ACT_TOOL = {
    "name": "act",
    "description": "Take the single next action toward the goal.",
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["navigate", "click", "type", "select", "extract", "wait", "done", "fail"],
            },
            "target": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "name": {"type": "string"},
                    "nth": {"type": "integer", "default": 0},
                    "exact": {"type": "boolean", "default": False},
                },
                "required": ["role", "name"],
            },
            "value": {"type": "string"},
            "extract_as": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["type", "reason"],
    },
}


class DiscoveryResult(BaseModel):
    status: Literal["success", "failure", "blocked"]
    goal: str
    outputs: dict
    steps: int
    reason: Optional[str] = None
    guardrail_violation: Optional[dict] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DiscoveryLog:
    """Append-only structured log of the run, written for /evidence/."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", encoding="utf-8")

    def write(self, **entry):
        entry["timestamp"] = _now()
        self._fh.write(json.dumps(entry) + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


def _create_with_retry(client: Anthropic, log: "DiscoveryLog", step: int, **kwargs):
    """
    Observed occasionally (non-reproducibly) on this API/SDK combination: a
    400 complaining a prior tool_use lacks a tool_result, even when the
    message list was independently verified correct via debug logging
    immediately before the call. Retrying the identical request has always
    succeeded, which points to a transient client/server hiccup rather than a
    structural bug in how we thread tool_use/tool_result pairs - so we retry
    a bounded number of times rather than let one flaky call kill the run.
    """
    last_error = None
    for attempt in range(3):
        try:
            return client.messages.create(**kwargs)
        except BadRequestError as e:
            last_error = e
            log.write(step=step, event="retry_after_error", attempt=attempt, error=str(e))
            time.sleep(1)
    raise last_error


def _state_message(surface: Surface, evidence_dir: Path, step: int) -> dict:
    state = surface.get_state(evidence_dir, step)
    text = (
        f"URL: {state.url}\nTitle: {state.title}\n\n"
        f"ARIA snapshot:\n{state.aria_snapshot[:4000]}"
    )
    return state, text


def run_discovery(
    goal: str,
    start_url: str,
    surface: Surface,
    evidence_dir: Path,
    max_steps: int = 15,
    client: Optional[Anthropic] = None,
    policy: Optional[GuardrailPolicy] = None,
) -> DiscoveryResult:
    client = client or Anthropic()
    policy = policy or GuardrailPolicy.load()
    log = DiscoveryLog(evidence_dir / "discovery_log.jsonl")
    outputs: dict = {}

    start_action = Action(type="navigate", value=start_url, reason="start")
    violation = check_discovery_action(policy, start_action, current_url="")
    if violation:
        log.write(step=0, event="guardrail_blocked", violation=violation.model_dump())
        log.close()
        return DiscoveryResult(
            status="blocked", goal=goal, outputs=outputs, steps=0,
            reason=f"guardrail: {violation.reason}", guardrail_violation=violation.model_dump(),
        )
    surface.act(start_action)
    state, state_text = _state_message(surface, evidence_dir, 0)
    log.write(step=0, event="state", url=state.url, title=state.title)

    messages = [
        {
            "role": "user",
            "content": f"GOAL: {goal}\n\nCurrent page:\n{state_text}",
        }
    ]

    try:
        for step in range(1, max_steps + 1):
            if os.environ.get("DISCOVERY_DEBUG"):
                print(f"--- step {step}: sending {len(messages)} messages ---")
                for i, m in enumerate(messages):
                    kind = type(m["content"]).__name__
                    print(f"  [{i}] role={m['role']} content_type={kind}")
                    if isinstance(m["content"], list):
                        for b in m["content"]:
                            print("      block:", b if isinstance(b, dict) else (b.type, getattr(b, "id", None)))
            response = _create_with_retry(
                client,
                log,
                step,
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=[ACT_TOOL],
                tool_choice={"type": "tool", "name": "act"},
                messages=messages,
            )
            if os.environ.get("DISCOVERY_DEBUG"):
                print(f"  response.stop_reason={response.stop_reason}")
                for b in response.content:
                    print("  block:", repr(b))
            tool_use = next(b for b in response.content if b.type == "tool_use")
            action = Action(
                type=tool_use.input["type"],
                target=ElementRef(**tool_use.input["target"]) if tool_use.input.get("target") else None,
                value=tool_use.input.get("value"),
                extract_as=tool_use.input.get("extract_as"),
                reason=tool_use.input.get("reason"),
            )
            messages.append({"role": "assistant", "content": response.content})
            log.write(step=step, event="decision", action=policy.redact_action(action))

            if action.type == "done":
                log.write(step=step, event="done", outputs=outputs)
                return DiscoveryResult(status="success", goal=goal, outputs=outputs, steps=step)

            if action.type == "fail":
                log.write(step=step, event="fail", reason=action.reason)
                return DiscoveryResult(
                    status="failure", goal=goal, outputs=outputs, steps=step, reason=action.reason
                )

            violation = check_discovery_action(policy, action, current_url=surface.page.url)
            if violation:
                log.write(step=step, event="guardrail_blocked", violation=violation.model_dump())
                return DiscoveryResult(
                    status="blocked", goal=goal, outputs=outputs, steps=step,
                    reason=f"guardrail: {violation.reason}", guardrail_violation=violation.model_dump(),
                )

            result = surface.act(action)
            if result.ok and action.type == "extract" and action.extract_as:
                outputs[action.extract_as] = result.extracted_value

            _, new_state_text = _state_message(surface, evidence_dir, step)
            log.write(step=step, event="result", ok=result.ok, error=result.error)

            result_text = (
                f"Result: {'ok' if result.ok else 'ERROR: ' + result.error}"
                + (f"\nExtracted: {result.extracted_value}" if result.extracted_value else "")
                + f"\n\nCurrent page:\n{new_state_text}"
            )
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": result_text,
                        }
                    ],
                }
            )

        log.write(step=max_steps, event="max_steps_reached")
        return DiscoveryResult(
            status="failure", goal=goal, outputs=outputs, steps=max_steps,
            reason="max steps reached without calling done",
        )
    finally:
        log.close()


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", required=True)
    parser.add_argument("--start-url", default="http://localhost:5000/login")
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--evidence-dir",
        default=f"evidence/runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}_discovery",
    )
    args = parser.parse_args()
    evidence_dir = Path(args.evidence_dir)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        surface = Surface(page)

        result = run_discovery(
            goal=args.goal,
            start_url=args.start_url,
            surface=surface,
            evidence_dir=evidence_dir,
            max_steps=args.max_steps,
        )
        browser.close()

    (evidence_dir / "run_result.json").write_text(result.model_dump_json(indent=2))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
