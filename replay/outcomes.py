"""
The replay result contract: a three-way distinction, per assignment 3.3.

- success: the checkpoint was met; outputs are returned.
- business_outcome: a known, expected non-success result (e.g. "no such
  member") - not a crash, a legitimate answer the caller needs.
- failure: something the artifact didn't anticipate. Stops and surfaces
  enough to debug: which step, what was expected, what was observed.
"""

from typing import Literal, Optional

from playwright.sync_api import Page
from pydantic import BaseModel

from artifacts.schema import CheckpointKind, KnownOutcome


class ErrorDetail(BaseModel):
    step_index: int
    action: str
    expected: str
    observed: str


class ReplayResult(BaseModel):
    status: Literal["success", "business_outcome", "failure", "blocked"]
    outputs: dict = {}
    outcome: Optional[str] = None  # KnownOutcome.name, when status == business_outcome
    error: Optional[ErrorDetail] = None  # when status == failure
    guardrail_violation: Optional[dict] = None  # when status == blocked


def check_condition(page: Page, kind: CheckpointKind, value: str) -> bool:
    if kind == "url_contains":
        return value in page.url
    body_text = page.locator("body").inner_text()
    if kind == "text_present":
        return value in body_text
    if kind == "text_absent":
        return value not in body_text
    raise ValueError(f"unknown checkpoint kind {kind!r}")


def match_known_outcome(page: Page, known_outcomes: list[KnownOutcome]) -> Optional[str]:
    for outcome in known_outcomes:
        if check_condition(page, outcome.kind, outcome.value):
            return outcome.name
    return None
