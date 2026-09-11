"""
Human-in-the-loop escalation and handoff (assignment 3.6).

The scope note explicitly allows mocking the operator UI as long as the
handoff mechanism and control-transfer model are real. The design here:

- The "operator surface" is a minimal command prompt, not a GUI - but the
  commands it accepts (click/type/select <role> <name> [value]) execute as
  real Action objects through the SAME Surface/page the automation was
  using, via Surface.act() - the identical code path discovery and replay
  already use. This is a real control transfer, not a simulation: nothing
  about the session is torn down or recreated, and it works whether the
  browser is headless or headed, so it's testable without a literal human.
- The command source is injectable (defaults to stdin) specifically so this
  can be proven to work with a scripted list of commands standing in for a
  human's input - see tests/test_handoff.py.
- control_state.json on disk is the answer to "who is in control": written
  "human" the moment escalation is raised, "automation" the moment resume
  is called. Nothing else reads or writes it while a handoff is in progress.
"""

import json
import shlex
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional

from pydantic import BaseModel

from agent.actions import Action, ElementRef
from agent.surface import Surface


class InterventionRequest(BaseModel):
    capability_id: Optional[str] = None
    goal: Optional[str] = None
    current_step: int
    reason: str
    screenshot_path: str
    page_url: str
    created_at: str = ""

    def model_post_init(self, __context) -> None:
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class HandoffLog:
    def __init__(self, path: Path):
        # Append, not overwrite: a single run (discovery or replay) can hit
        # more than one escalation - e.g. a model retrying the same blocked
        # action - and each one gets its own HandoffLog instance. Opening
        # "w" here silently discarded every earlier escalation's log
        # entries the moment a second one occurred in the same run.
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")

    def write(self, **entry):
        entry["timestamp"] = datetime.now().isoformat()
        self._fh.write(json.dumps(entry, default=str) + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()


def _set_control(evidence_dir: Path, control: str, reason: str = "") -> None:
    (evidence_dir / "control_state.json").write_text(
        json.dumps({"control": control, "since": datetime.now().isoformat(), "reason": reason}, indent=2)
    )


def _parse_operator_command(line: str) -> Action:
    # shlex, not str.split: accessible names are usually multiple words and
    # must be quotable, e.g. click button "Confirm and Open Account".
    parts = shlex.split(line)
    cmd = parts[0]
    if cmd not in ("click", "type", "select"):
        raise ValueError(f"unknown operator command {cmd!r} (try: click/type/select <role> <name> [value])")
    if len(parts) < 3:
        raise ValueError(f'usage: {cmd} <role> "<name>" [value]')
    role, name = parts[1], parts[2]
    value = parts[3] if len(parts) > 3 else None
    return Action(type=cmd, target=ElementRef(role=role, name=name), value=value)


def _stdin_commands() -> Iterator[str]:
    while True:
        try:
            yield input("operator> ")
        except EOFError:
            return


def run_operator_session(
    surface: Surface, commands: Iterable[str], evidence_dir: Path, log: HandoffLog,
) -> list[dict]:
    """
    Executes operator commands against the live surface until 'resume'.
    Returns the history of what the human did - the record the assignment
    asks for ("record what the human did").
    """
    history: list[dict] = []
    for raw in commands:
        line = raw.strip()
        if not line:
            continue
        print(f"[operator] > {line}")
        if line == "resume":
            log.write(event="operator_resume")
            break
        if line == "state":
            state = surface.get_state()
            print(f"URL: {state.url}\n{state.aria_snapshot[:2000]}")
            continue
        if line == "screenshot":
            path = evidence_dir / f"operator_{len(history):03d}.png"
            surface.page.screenshot(path=str(path))
            print(f"saved {path}")
            continue
        try:
            action = _parse_operator_command(line)
            result = surface.act(action)
            history.append({"command": line, "ok": result.ok, "error": result.error})
            log.write(event="operator_action", command=line, ok=result.ok, error=result.error)
            print("ok" if result.ok else f"ERROR: {result.error}")
        except Exception as e:
            print(f"error: {e}")
            history.append({"command": line, "ok": False, "error": str(e)})
    return history


def escalate(
    surface: Surface,
    request: InterventionRequest,
    evidence_dir: Path,
    commands: Optional[Iterable[str]] = None,
) -> list[dict]:
    """
    Pauses automation, raises the intervention request, hands the live
    session to a human (via the operator command prompt), and returns what
    they did once they signal 'resume'. `commands` defaults to stdin for
    real use; tests pass a scripted list to prove this deterministically.
    """
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # Per-step filename for the same reason HandoffLog now appends: more
    # than one escalation can happen in a single run, and each one's
    # request deserves to survive, not just the most recent.
    request_path = evidence_dir / f"intervention_request_step_{request.current_step:03d}.json"
    request_path.write_text(request.model_dump_json(indent=2))
    _set_control(evidence_dir, "human", reason=request.reason)

    print("=" * 70)
    print("ESCALATION: automation paused, human intervention requested")
    print(f"Reason: {request.reason}")
    print(f"Step: {request.current_step}  URL: {request.page_url}")
    print(f"Screenshot: {request.screenshot_path}")
    print("Commands: click/type/select <role> <name> [value] | state | screenshot | resume")
    print("=" * 70)

    log = HandoffLog(evidence_dir / "handoff_log.jsonl")
    log.write(event="escalation_raised", request=request.model_dump())

    history = run_operator_session(surface, commands or _stdin_commands(), evidence_dir, log)

    _set_control(evidence_dir, "automation")
    log.write(event="control_returned", human_actions=history)
    log.close()
    return history
