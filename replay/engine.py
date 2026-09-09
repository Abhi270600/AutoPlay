"""
Deterministic replay: executes a saved CapabilityArtifact step by step, with
no LLM in the decision loop. Every action is already decided; this only has
to locate elements, act, and verify - the same Surface-level primitives
(Playwright) as discovery, but driven by the artifact instead of a model.
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from playwright.sync_api import Locator, Page, sync_playwright

from agent.guardrails import GuardrailPolicy, check_replay_step
from agent.surface import Surface
from artifacts.schema import ArtifactStep, CapabilityArtifact, TargetLocator
from escalation.handoff import InterventionRequest, escalate
from replay.outcomes import ErrorDetail, ReplayResult, check_condition, match_known_outcome

PARAM_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _substitute(value: Optional[str], params: dict) -> Optional[str]:
    if value is None:
        return None
    return PARAM_PATTERN.sub(lambda m: str(params[m.group(1)]), value)


def _resolve(page: Page, target: TargetLocator) -> Locator:
    locator = page.get_by_role(target.role, name=target.name, exact=target.exact).nth(target.nth)
    if target.relative == "next_cell":
        # The anchor is found by role+name (stable); this last hop is a DOM
        # sibling lookup, which is fine precisely because it's relative to
        # an already-reliably-found element, not an absolute path.
        locator = locator.locator("xpath=following-sibling::*[1]")
    return locator


def _run_step(page: Page, step: ArtifactStep, params: dict, outputs: dict) -> None:
    value = _substitute(step.value, params)
    locator = _resolve(page, step.target) if step.target else None

    if step.action == "navigate":
        page.goto(value)
    elif step.action == "click":
        locator.click()
    elif step.action == "type":
        locator.fill(value or "")
    elif step.action == "select":
        locator.select_option(label=value)
    elif step.action == "extract":
        outputs[step.extract_as] = locator.inner_text().strip()
    elif step.action == "wait":
        page.wait_for_timeout(int(value or "1000"))
    else:
        raise ValueError(f"unknown step action {step.action!r}")


class ReplayLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8")

    def write(self, **entry):
        entry["timestamp"] = datetime.now().isoformat()
        self._fh.write(json.dumps(entry) + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


def run_replay(
    artifact: CapabilityArtifact,
    params: dict,
    page: Page,
    evidence_dir: Optional[Path] = None,
    policy: Optional[GuardrailPolicy] = None,
    escalation_commands: Optional[Iterable[str]] = None,
) -> ReplayResult:
    policy = policy or GuardrailPolicy.load()
    log = ReplayLog(evidence_dir / "replay_log.jsonl") if evidence_dir else None
    outputs: dict = {}
    surface = Surface(page)
    handoff_dir = (evidence_dir or Path("evidence/_tmp_replay")) / "handoff"

    missing = [p.name for p in artifact.input_params if p.required and p.name not in params]
    if missing:
        raise ValueError(f"missing required input params: {missing}")

    entry_url = artifact.target.base_url + artifact.target.entry_point
    if not policy.is_url_allowed(entry_url):
        if log:
            log.write(step=0, event="guardrail_blocked", detail=f"entry point {entry_url} not allowed")
            log.close()
        return ReplayResult(
            status="blocked",
            guardrail_violation={"reason": "url_not_allowed", "detail": f'"{entry_url}" is outside the allowlist'},
        )

    try:
        page.goto(entry_url)
    except Exception as e:
        if log:
            log.write(step=0, action="navigate", ok=False, error=str(e))
            log.close()
        return ReplayResult(
            status="failure",
            error=ErrorDetail(
                step_index=0, action="navigate",
                expected=f"reach entry point {entry_url}",
                observed=f"{type(e).__name__}: {e}",
            ),
        )

    try:
        for step in artifact.steps:
            violation = check_replay_step(policy, step, current_url=page.url)
            if violation:
                if log:
                    log.write(step=step.index, event="guardrail_blocked", violation=violation.model_dump())
                screenshot_path = handoff_dir / f"escalation_step_{step.index:03d}.png"
                handoff_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot_path))
                request = InterventionRequest(
                    capability_id=artifact.id, current_step=step.index,
                    reason=f"guardrail: {violation.reason} - {violation.detail}",
                    screenshot_path=str(screenshot_path), page_url=page.url,
                )
                # A block means a person must decide this step's fate - not
                # retry it automatically. If they act via the operator
                # session, that IS the step; if they decline, we move on
                # without it. Either way replay does not perform it itself.
                escalate(surface, request, handoff_dir, escalation_commands)
                if log:
                    log.write(step=step.index, event="escalation_resolved", action="skipped_after_human_decision")
                continue

            try:
                _run_step(page, step, params, outputs)
                if log:
                    log.write(step=step.index, action=step.action, ok=True)
            except Exception as e:
                if log:
                    log.write(step=step.index, action=step.action, ok=False, error=str(e))
                if evidence_dir:
                    page.screenshot(path=str(evidence_dir / f"failure_step_{step.index:03d}.png"))

                outcome = match_known_outcome(page, artifact.known_outcomes)
                if outcome:
                    if log:
                        log.write(event="business_outcome", outcome=outcome)
                    return ReplayResult(status="business_outcome", outcome=outcome)

                target_desc = (
                    f'role="{step.target.role}" name="{step.target.name}"' if step.target else "(no target)"
                )

                # Not a known outcome and not policy-blocked - this is exactly
                # "a condition it can't recover from" (assignment 3.6): escalate,
                # then retry the SAME step once, since the human's fix (e.g.
                # dismissing a stuck dialog) should let the original step
                # succeed now. Retry, not skip - unlike the guardrail-block
                # case above, nothing says this step was already done for us.
                handoff_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = handoff_dir / f"escalation_step_{step.index:03d}.png"
                page.screenshot(path=str(screenshot_path))
                request = InterventionRequest(
                    capability_id=artifact.id, current_step=step.index,
                    reason=f"unrecoverable error at step {step.index} ({step.action}): {e}",
                    screenshot_path=str(screenshot_path), page_url=page.url,
                )
                escalate(surface, request, handoff_dir, escalation_commands)

                try:
                    _run_step(page, step, params, outputs)
                    if log:
                        log.write(step=step.index, action=step.action, ok=True, note="succeeded after escalation")
                    continue
                except Exception as e2:
                    if log:
                        log.write(step=step.index, action=step.action, ok=False, error=str(e2), note="failed again after escalation")
                    return ReplayResult(
                        status="failure",
                        error=ErrorDetail(
                            step_index=step.index, action=step.action,
                            expected=f"step {step.index} ({step.action}) to succeed against {target_desc} (even after human escalation)",
                            observed=f"{type(e2).__name__}: {e2}",
                        ),
                    )

        checkpoint_met = check_condition(page, artifact.checkpoint.kind, artifact.checkpoint.value)
        if not checkpoint_met:
            outcome = match_known_outcome(page, artifact.known_outcomes)
            if outcome:
                if log:
                    log.write(event="business_outcome", outcome=outcome)
                return ReplayResult(status="business_outcome", outcome=outcome)

            if evidence_dir:
                page.screenshot(path=str(evidence_dir / "failure_checkpoint.png"))
            return ReplayResult(
                status="failure",
                error=ErrorDetail(
                    step_index=len(artifact.steps), action="checkpoint",
                    expected=f"{artifact.checkpoint.kind}={artifact.checkpoint.value!r}",
                    observed=f"not met at url={page.url}",
                ),
            )

        if log:
            log.write(event="success", outputs=outputs)
        return ReplayResult(status="success", outputs=outputs)
    finally:
        if log:
            log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--param", action="append", default=[], metavar="name=value")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--evidence-dir",
        default=f"evidence/runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}_replay",
    )
    args = parser.parse_args()

    artifact = CapabilityArtifact.model_validate_json(Path(args.artifact).read_text())
    params = dict(p.split("=", 1) for p in args.param)
    evidence_dir = Path(args.evidence_dir)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        result = run_replay(artifact, params, page, evidence_dir)
        browser.close()

    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "replay_result.json").write_text(result.model_dump_json(indent=2))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
