"""
Agent-facing capability interface (optional stretch goal, assignment 8).

Everywhere else, a capability is triggered by a human typing a CLI command
with a file path and --param flags. That's fine for a person at a terminal,
but it's not something other software can realistically do - it would have
to build a shell command as text and scrape printed output back out. This
module is the thin layer the assignment's own opening paragraph describes:
"the AI agents can invoke [a capability] on demand... without re-reasoning
about the UI every time." Two functions, no new automation logic:

- build_catalog() turns every saved artifact into a tool definition shaped
  exactly like an Anthropic API tool (name, description, input_schema) -
  droppable directly into a real `tools=[...]` list for any Claude-based
  agent, the same shape agent/discovery.py's own ACT_TOOL uses.
- invoke(name, **kwargs) finds the matching artifact and runs it through
  the existing, unmodified replay engine. This is not a new execution
  path; it's the same run_replay() every replay CLI command already uses.

Deciding *which* capability matches a goal is the calling agent's own job,
the same way agent/discovery.py's model already picks between click/type/
select from a tool description - this module only makes capabilities
describable and callable, it doesn't add a new decision-maker.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from artifacts.schema import CapabilityArtifact, ParamSpec
from replay.engine import run_replay
from replay.outcomes import ReplayResult

STORE_DIR = Path("artifacts/store")

_JSON_TYPE = {"string": "string", "number": "number", "boolean": "boolean"}


def _input_schema(params: list[ParamSpec]) -> dict:
    properties = {p.name: {"type": _JSON_TYPE[p.type], "description": p.description} for p in params}
    required = [p.name for p in params if p.required]
    return {"type": "object", "properties": properties, "required": required}


def _latest_artifacts(store_dir: Path = STORE_DIR) -> dict[str, CapabilityArtifact]:
    """One entry per capability id: the highest version found for each."""
    latest: dict[str, CapabilityArtifact] = {}
    for f in sorted(store_dir.glob("*.json")):
        artifact = CapabilityArtifact.model_validate_json(f.read_text())
        current = latest.get(artifact.id)
        if current is None or artifact.version > current.version:
            latest[artifact.id] = artifact
    return latest


def build_catalog(store_dir: Path = STORE_DIR) -> list[dict]:
    """
    Every saved capability as an Anthropic-shaped tool definition. Pass this
    list straight into a real `tools=[...]` call for a Claude-based agent to
    discover and choose between them.
    """
    catalog = []
    for artifact in _latest_artifacts(store_dir).values():
        outputs_desc = (
            " Returns: " + ", ".join(f"{o.name} ({o.description})" for o in artifact.outputs)
            if artifact.outputs else ""
        )
        catalog.append({
            "name": artifact.id,
            "description": artifact.description + outputs_desc,
            "input_schema": _input_schema(artifact.input_params),
        })
    return catalog


def invoke(name: str, evidence_dir: Optional[Path] = None, headless: bool = True, **params) -> ReplayResult:
    """
    Runs a saved capability by name with typed arguments - the same call
    shape a tool-calling agent would use. Executes through the real,
    unmodified replay engine: no LLM involved, fully deterministic.
    """
    artifacts = _latest_artifacts()
    if name not in artifacts:
        raise ValueError(f"no capability named {name!r}; available: {sorted(artifacts)}")
    artifact = artifacts[name]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        result = run_replay(artifact, params, page, evidence_dir=evidence_dir)
        browser.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("catalog", help="print the tool catalog every saved capability exposes")

    invoke_parser = sub.add_parser("invoke", help="run one capability by name")
    invoke_parser.add_argument("name", help="capability id, e.g. lookup-member-savings-balance")
    invoke_parser.add_argument("--param", action="append", default=[], metavar="name=value")
    invoke_parser.add_argument("--headed", action="store_true")
    invoke_parser.add_argument(
        "--evidence-dir",
        default=None,
        help="defaults to evidence/runs/<timestamp>_invoke_<name>/; pass an empty string to skip evidence entirely",
    )

    args = parser.parse_args()

    if args.command == "catalog":
        print(json.dumps(build_catalog(), indent=2))
        return

    params = dict(p.split("=", 1) for p in args.param)
    if args.evidence_dir is None:
        evidence_dir = Path(f"evidence/runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}_invoke_{args.name}")
    elif args.evidence_dir == "":
        evidence_dir = None
    else:
        evidence_dir = Path(args.evidence_dir)

    result = invoke(args.name, evidence_dir=evidence_dir, headless=not args.headed, **params)

    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "invoke_result.json").write_text(result.model_dump_json(indent=2))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
