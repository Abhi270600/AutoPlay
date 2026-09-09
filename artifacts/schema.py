"""
The capability artifact: a typed, versioned, agent-invocable description of a
flow, decoupled from the raw discovery transcript (per assignment 3.2). This
schema - not the discovery loop - is the focal point of the evaluation, so
its shape is deliberate:

- `steps` capture how to act, with a `TargetLocator` that carries explicit
  robustness reasoning, not just a bare selector.
- `input_params` / `outputs` are the typed contract a calling agent sees -
  what it must supply and what it gets back - independent of how the flow
  is internally recorded.
- `checkpoint` is the one thing the replay engine trusts to say "this
  actually worked," decoupled from "the click didn't throw."
"""

from typing import Literal, Optional

from pydantic import BaseModel

ParamType = Literal["string", "number", "boolean"]
StepAction = Literal["navigate", "click", "type", "select", "extract", "wait"]
CheckpointKind = Literal["text_present", "text_absent", "url_contains"]


class ParamSpec(BaseModel):
    name: str
    type: ParamType
    description: str
    required: bool = True


class TargetLocator(BaseModel):
    """
    How a step's element is identified for replay, plus *why* that's expected
    to be robust - required reading for whoever reviews this artifact, human
    or agent.
    """

    role: str
    name: str
    nth: int = 0
    exact: bool = False
    # If set, role/name/exact identify a stable *anchor* element (e.g. a
    # label cell) rather than the target itself, and the target is resolved
    # relative to it. Needed because a value like a balance has no accessible
    # name that's independent of the data - "$4231.00" only matches member
    # 12345's page. "next_cell" = the adjacent table cell in the anchor's row.
    # Replay resolves this (see replay/engine.py); Surface does not need it
    # for live discovery, where the model re-observes the page every step.
    relative: Optional[Literal["next_cell"]] = None
    reasoning: str


class ArtifactStep(BaseModel):
    index: int
    action: StepAction
    target: Optional[TargetLocator] = None
    value: Optional[str] = None  # literal, or a "{{param_name}}" placeholder
    extract_as: Optional[str] = None  # ties this step's result to an output


class TargetSpec(BaseModel):
    base_url: str
    entry_point: str  # path to start the flow at, relative to base_url


class Provenance(BaseModel):
    discovery_run_id: str
    model: str
    recorded_at: str


class Checkpoint(BaseModel):
    kind: CheckpointKind
    value: str


class CapabilityArtifact(BaseModel):
    id: str
    version: int
    description: str
    target: TargetSpec
    provenance: Provenance
    input_params: list[ParamSpec]
    steps: list[ArtifactStep]
    outputs: list[ParamSpec]
    checkpoint: Checkpoint
