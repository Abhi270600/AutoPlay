"""
Typed vocabulary shared by the discovery loop, the Surface, and (later) the
replay engine and artifact schema. Keeping this small and shared is what lets
a recorded step be replayed later without re-interpreting a raw model action.
"""

from typing import Literal, Optional

from pydantic import BaseModel


class ElementRef(BaseModel):
    """
    Identifies a target element the way accessibility APIs do: by role and
    accessible name, not by pixel position or a brittle CSS path. This is the
    locator strategy used both to act on an element and, later, to record it
    in a capability artifact.
    """

    role: str  # ARIA role: "textbox", "button", "combobox", "link", ...
    name: str  # accessible name (visible label text, aria-label, or value)
    nth: int = 0  # disambiguates when more than one element shares role+name
    exact: bool = False  # require an exact name match, not substring - see
    # Surface._locate: nested tables mean an ancestor <td>'s accessible name
    # often contains a descendant <td>'s name as a substring, so substring
    # matching alone is not reliable for picking a specific cell.


ActionType = Literal[
    "navigate", "click", "type", "select", "extract", "wait", "done", "fail"
]


class Action(BaseModel):
    type: ActionType
    target: Optional[ElementRef] = None
    value: Optional[str] = None  # URL for navigate, text for type/select
    extract_as: Optional[str] = None  # output key name, for "extract" actions
    reason: Optional[str] = None  # model's stated reasoning, for the log


class ActionResult(BaseModel):
    ok: bool
    error: Optional[str] = None
    extracted_value: Optional[str] = None
