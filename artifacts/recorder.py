"""
Converts a successful discovery run's log into a saved CapabilityArtifact.

Deliberately manual, not automatic, in two ways - both are curation
decisions a human makes when promoting a raw discovery run into a reusable
production capability, not something inferred from the transcript alone:

1. Which literal values become input parameters (`param_bindings`) - e.g.
   the member ID typed during discovery is *the* thing a caller should
   supply per invocation, but the dummy sign-on credentials are not.
2. Locator overrides (`target_overrides`) - discovery sometimes lands on a
   locator that only worked because of what happened to be on screen (see
   artifacts/schema.py's `relative` field docstring). Recording is where
   that gets caught and fixed, before it becomes a production capability.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from artifacts.schema import (
    ArtifactStep,
    CapabilityArtifact,
    Checkpoint,
    ParamSpec,
    Provenance,
    TargetLocator,
    TargetSpec,
)


def _load_decisions(log_path: Path) -> list[dict]:
    decisions = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("event") == "decision":
                decisions.append(entry)
    return decisions


def _default_reasoning(t: dict) -> str:
    reasoning = (
        f'Targets by ARIA role "{t["role"]}" + accessible name "{t["name"]}", '
        "not a CSS/XPath selector - the accessibility tree is exposed by the "
        "browser/OS directly and survives this app's markup changes better "
        "than a selector tied to its table-based layout."
    )
    if t.get("exact"):
        reasoning += (
            " Exact name match required: this app's nested tables mean an "
            "ancestor cell's accessible name can contain this text as a "
            "substring, so a loose match would resolve to the wrong element."
        )
    return reasoning


def build_artifact(
    capability_id: str,
    version: int,
    description: str,
    discovery_run_dir: Path,
    model: str,
    target_base_url: str,
    entry_point: str,
    param_bindings: dict[int, ParamSpec],
    output_specs: dict[str, ParamSpec],
    checkpoint: Checkpoint,
    target_overrides: Optional[dict[int, TargetLocator]] = None,
) -> CapabilityArtifact:
    target_overrides = target_overrides or {}
    decisions = _load_decisions(discovery_run_dir / "discovery_log.jsonl")

    steps: list[ArtifactStep] = []
    input_params: list[ParamSpec] = []
    outputs: list[ParamSpec] = []
    seen_params = set()

    for d in decisions:
        step_idx = d["step"]
        action = d["action"]
        if action["type"] in ("done", "fail"):
            continue

        if step_idx in target_overrides:
            target = target_overrides[step_idx]
        elif action.get("target"):
            t = action["target"]
            target = TargetLocator(
                role=t["role"], name=t["name"], nth=t.get("nth", 0),
                exact=t.get("exact", False), reasoning=_default_reasoning(t),
            )
        else:
            target = None

        value = action.get("value")
        if step_idx in param_bindings:
            param = param_bindings[step_idx]
            value = "{{" + param.name + "}}"
            if param.name not in seen_params:
                input_params.append(param)
                seen_params.add(param.name)

        steps.append(
            ArtifactStep(
                index=step_idx, action=action["type"], target=target,
                value=value, extract_as=action.get("extract_as"),
            )
        )

        extract_as = action.get("extract_as")
        if action["type"] == "extract" and extract_as:
            outputs.append(
                output_specs.get(
                    extract_as,
                    ParamSpec(name=extract_as, type="string", description=extract_as),
                )
            )

    return CapabilityArtifact(
        id=capability_id,
        version=version,
        description=description,
        target=TargetSpec(base_url=target_base_url, entry_point=entry_point),
        provenance=Provenance(
            discovery_run_id=discovery_run_dir.name,
            model=model,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        ),
        input_params=input_params,
        steps=steps,
        outputs=outputs,
        checkpoint=checkpoint,
    )


if __name__ == "__main__":
    # Records the one capability discovered so far. As more capabilities are
    # added, each gets a block like this - there are too few of them yet to
    # justify a generic config-driven recording CLI.
    artifact = build_artifact(
        capability_id="lookup-member-savings-balance",
        version=1,
        description=(
            "Signs on to the CoreServ member servicing terminal, looks up a "
            "member by ID, and returns their current savings balance."
        ),
        discovery_run_dir=Path("evidence/runs/20260909_110340_discovery"),
        model="claude-haiku-4-5-20251001",
        target_base_url="http://localhost:5000",
        entry_point="/login",
        param_bindings={
            2: ParamSpec(name="operator_id", type="string", description="Operator ID to sign on with"),
            4: ParamSpec(name="operator_password", type="string", description="Operator password to sign on with"),
            7: ParamSpec(name="member_id", type="string", description="Member ID to look up"),
        },
        output_specs={
            "savings_balance": ParamSpec(
                name="savings_balance", type="string",
                description="Current savings balance, formatted as currency (e.g. \"$4231.00\")",
            ),
        },
        checkpoint=Checkpoint(kind="text_present", value="Savings Balance"),
        target_overrides={
            9: TargetLocator(
                role="cell", name="Savings Balance:", exact=True, relative="next_cell",
                reasoning=(
                    "Discovery targeted the balance's own text (\"$4231.00\"), which "
                    "only matches this one member's page. Overridden at recording "
                    "time to anchor on the stable label cell \"Savings Balance:\" and "
                    "take the adjacent cell - independent of which member is looked up."
                ),
            ),
        },
    )

    out_path = Path("artifacts/store") / f"{artifact.id}.v{artifact.version}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(artifact.model_dump_json(indent=2))
    print(f"Wrote {out_path}")
