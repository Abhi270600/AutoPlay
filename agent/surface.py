"""
The Surface: the one place that knows how to perceive and act on a live page.

This is the seam between "how we perceive/act on a surface" and "the recorded
flow" (see REPORT.md, Heterogeneity & multi-tenant). The discovery loop and the
replay engine both talk to a Surface and never touch Playwright directly - so a
future surface backed by a desktop accessibility API instead of a browser could
implement the same get_state()/act() contract without changing either of them.

Perception is accessibility-tree-first (an ARIA snapshot), not screenshot-first:
legacy apps rarely have a clean DOM, but the accessibility tree is usually still
there because it's a platform-level API, not something the app author opts into.
A screenshot is captured alongside purely as evidence, not as the locator source.
"""

from pathlib import Path
from typing import Optional

from playwright.sync_api import Page
from pydantic import BaseModel

from agent.actions import Action, ActionResult, ElementRef


class PageState(BaseModel):
    url: str
    title: str
    aria_snapshot: str
    screenshot_path: Optional[str] = None


class ElementNotFound(Exception):
    pass


class Surface:
    def __init__(self, page: Page):
        self.page = page

    def get_state(self, evidence_dir: Optional[Path] = None, step: int = 0) -> PageState:
        screenshot_path = None
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = str(evidence_dir / f"step_{step:03d}.png")
            self.page.screenshot(path=screenshot_path)

        return PageState(
            url=self.page.url,
            title=self.page.title(),
            aria_snapshot=self.page.locator("body").aria_snapshot(),
            screenshot_path=screenshot_path,
        )

    def _locate(self, ref: ElementRef):
        locator = self.page.get_by_role(ref.role, name=ref.name, exact=ref.exact).nth(ref.nth)
        if locator.count() == 0:
            raise ElementNotFound(f"no element with role={ref.role!r} name={ref.name!r}")
        return locator

    def act(self, action: Action) -> ActionResult:
        try:
            if action.type == "navigate":
                self.page.goto(action.value)
            elif action.type == "click":
                self._locate(action.target).click()
            elif action.type == "type":
                self._locate(action.target).fill(action.value or "")
            elif action.type == "select":
                self._locate(action.target).select_option(label=action.value)
            elif action.type == "extract":
                text = self._locate(action.target).inner_text()
                return ActionResult(ok=True, extracted_value=text.strip())
            elif action.type == "wait":
                self.page.wait_for_timeout(int(action.value or "1000"))
            elif action.type in ("done", "fail"):
                pass  # terminal actions - nothing to execute against the page
            else:
                return ActionResult(ok=False, error=f"unknown action type {action.type!r}")
            return ActionResult(ok=True)
        except ElementNotFound as e:
            return ActionResult(ok=False, error=str(e))
        except Exception as e:  # Playwright timeouts, detached elements, etc.
            return ActionResult(ok=False, error=f"{type(e).__name__}: {e}")

    def page_contains_text(self, text: str) -> bool:
        return text in self.page.locator("body").inner_text()
