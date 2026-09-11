"""
Real proof that an AI agent - not a human - can pick and invoke the right
capability from a plain-English request, using capabilities.interface's own
catalog as the actual tool list a live Claude call reasons over.

Every other test of this interface had a human pick the capability name and
type the arguments. This is the one that closes that gap: Claude sees the
same catalog build_catalog() produces (already shaped as real Anthropic tool
definitions), a plain-English request, and has to choose which capability
fits and fill in its arguments itself, the same forced-tool-calling pattern
agent/discovery.py already uses for individual clicks, just one level up.

Needs the mock app running on http://localhost:5000 and ANTHROPIC_API_KEY
set. Costs one real API call, comparable to a single discovery step.

Run with a request of your own:
    PYTHONPATH=. python scripts/demo_agent_calls_capability.py "your request here"
Or with no argument, to use the default request below:
    PYTHONPATH=. python scripts/demo_agent_calls_capability.py
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from capabilities.interface import build_catalog, invoke

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

DEFAULT_REQUEST = (
    'Please check member 23456\'s current savings balance. '
    'Sign on as operator "tester" with password "x".'
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("request", nargs="?", default=DEFAULT_REQUEST, help="the plain-English goal to hand the agent")
args = parser.parse_args()
user_request = args.request

catalog = build_catalog()
print("=== Tools offered to the model (this system's real capability catalog) ===")
for tool in catalog:
    print(f"- {tool['name']}: {tool['description'][:90]}...")

client = Anthropic()
response = client.messages.create(
    model=MODEL,
    max_tokens=1024,
    system=(
        "You are an AI agent for a bank. You have access to a set of tools, each one a "
        "real, pre-built capability for operating the bank's servicing system. Given a "
        "user's request, pick the single correct tool and call it with the correct "
        "arguments. Do not guess at capabilities that aren't offered to you."
    ),
    tools=catalog,
    tool_choice={"type": "any"},
    messages=[{"role": "user", "content": user_request}],
)

evidence_dir = Path(f"evidence/runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}_agent_call")
evidence_dir.mkdir(parents=True, exist_ok=True)

tool_use = next((b for b in response.content if b.type == "tool_use"), None)
print("\n=== Claude's decision ===")
print(f"User asked: {user_request!r}")

if tool_use is None:
    print("Claude did not call any tool - it may have replied in text instead. Full response:")
    print(response.content)
    (evidence_dir / "agent_decision.json").write_text(json.dumps({
        "user_request": user_request, "tool_called": None, "raw_response": str(response.content),
    }, indent=2))
else:
    print(f"Claude chose capability: {tool_use.name!r}")
    print(f"Claude chose arguments: {tool_use.input}")
    (evidence_dir / "agent_decision.json").write_text(json.dumps({
        "user_request": user_request, "capability_chosen": tool_use.name, "arguments_chosen": tool_use.input,
    }, indent=2))

    print("\n=== Actually invoking what Claude chose ===")
    # Same evidence_dir as the decision above, so the model's reasoning and
    # the actual replay run (screenshots, replay_log.jsonl) it triggered
    # live together - this is the one thing calling invoke() directly,
    # instead of through `python -m capabilities.interface invoke`, would
    # otherwise silently skip: evidence_dir defaults to None.
    result = invoke(tool_use.name, evidence_dir=evidence_dir, **tool_use.input)
    (evidence_dir / "invoke_result.json").write_text(result.model_dump_json(indent=2))
    print(result.model_dump_json(indent=2))
    print(f"\nDone - capability {tool_use.name!r} ran with status {result.status!r}.")
    print(f"Evidence written to {evidence_dir}")
