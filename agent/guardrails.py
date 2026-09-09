"""
Guardrail policy: allowlist enforcement, risk classification, and redaction.

Both the discovery loop and the replay engine call check_discovery_action() /
check_replay_step() immediately before executing anything against the real
page - this is the one checkpoint neither loop can bypass, not something
folded into Surface (which stays a dumb perceive/act mechanism).
"""

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel

from agent.actions import Action
from artifacts.schema import ArtifactStep


class RiskyTarget(BaseModel):
    role: str
    name: str


class GuardrailViolation(BaseModel):
    reason: Literal["action_type_not_allowed", "url_not_allowed", "risky_action_blocked"]
    detail: str


class GuardrailPolicy(BaseModel):
    allowed_base_urls: list[str]
    allowed_routes: list[str]
    allowed_action_types: list[str]
    risky_targets: list[RiskyTarget]
    sensitive_field_patterns: list[str]

    @classmethod
    def load(cls, path: Path = Path("config/allowlist.yaml")) -> "GuardrailPolicy":
        return cls(**yaml.safe_load(path.read_text()))

    def is_url_allowed(self, url: str) -> bool:
        if not any(url.startswith(base) for base in self.allowed_base_urls):
            return False
        path = "/" + url.split("://", 1)[-1].split("/", 1)[-1] if "/" in url.split("://", 1)[-1] else "/"
        path = path.split("?", 1)[0]
        return any(_route_matches(pattern, path) for pattern in self.allowed_routes)

    def is_action_type_allowed(self, action_type: str) -> bool:
        return action_type in self.allowed_action_types

    def is_risky_target(self, role: Optional[str], name: Optional[str]) -> bool:
        return any(r.role == role and r.name == name for r in self.risky_targets)

    def is_sensitive_field(self, name: Optional[str]) -> bool:
        if not name:
            return False
        lowered = name.lower()
        return any(p in lowered for p in self.sensitive_field_patterns)

    def redact_action(self, action: Action) -> dict:
        data = action.model_dump()
        if action.target and self.is_sensitive_field(action.target.name) and data.get("value"):
            data["value"] = "[REDACTED]"
        return data


def _route_matches(pattern: str, path: str) -> bool:
    import re

    regex = "^" + re.escape(pattern).replace(r"\*", "[^/]+") + "$"
    return re.match(regex, path) is not None


def check_discovery_action(
    policy: GuardrailPolicy, action: Action, current_url: str
) -> Optional[GuardrailViolation]:
    if action.type in ("done", "fail"):
        return None
    if not policy.is_action_type_allowed(action.type):
        return GuardrailViolation(
            reason="action_type_not_allowed",
            detail=f'"{action.type}" is not in allowed_action_types',
        )
    url_to_check = action.value if action.type == "navigate" else current_url
    if not policy.is_url_allowed(url_to_check):
        return GuardrailViolation(
            reason="url_not_allowed", detail=f'"{url_to_check}" is outside the allowlist',
        )
    if action.target and policy.is_risky_target(action.target.role, action.target.name):
        return GuardrailViolation(
            reason="risky_action_blocked",
            detail=f'target role="{action.target.role}" name="{action.target.name}" is '
            "classified risky and is blocked pending human confirmation",
        )
    return None


def check_replay_step(
    policy: GuardrailPolicy, step: ArtifactStep, current_url: str
) -> Optional[GuardrailViolation]:
    if not policy.is_action_type_allowed(step.action):
        return GuardrailViolation(
            reason="action_type_not_allowed",
            detail=f'"{step.action}" is not in allowed_action_types',
        )
    url_to_check = step.value if step.action == "navigate" else current_url
    if not policy.is_url_allowed(url_to_check):
        return GuardrailViolation(
            reason="url_not_allowed", detail=f'"{url_to_check}" is outside the allowlist',
        )
    if step.target and policy.is_risky_target(step.target.role, step.target.name):
        return GuardrailViolation(
            reason="risky_action_blocked",
            detail=f'target role="{step.target.role}" name="{step.target.name}" is '
            "classified risky and is blocked pending human confirmation",
        )
    return None
