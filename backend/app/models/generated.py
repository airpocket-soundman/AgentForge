"""Models for AI-generated features (real self-expansion).

A generated feature = a `ViewManifest` (what the UI Designer worker produces) plus
schema-flexible entities stored via the generic CRUD. This is what makes adding an
arbitrary feature (e.g. a Gantt chart) actually work — no hand-written code per
feature.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FieldType = Literal["text", "textarea", "number", "date", "checkbox", "markdown"]
ChartType = Literal["bar", "line", "pie", "doughnut"]
StatAgg = Literal["sum", "count", "avg"]


class FieldSpec(BaseModel):
    key: str
    label: str
    type: FieldType = "text"


class ChartSpec(BaseModel):
    """Standard chart component (Chart.js). The LLM only declares config — no code."""

    type: ChartType = "bar"
    title: str = ""
    category: str  # field key used for labels (x / slice)
    value: str     # numeric field key used for values (summed per category)


class StatSpec(BaseModel):
    """KPI/metric tile: an aggregate of one field over all entities."""

    label: str
    value: str            # field key (numeric for sum/avg; any for count)
    agg: StatAgg = "sum"


class GanttSpec(BaseModel):
    """Gantt/timeline: horizontal bars from start..end per row."""

    label: str  # field key for the row label
    start: str  # date field key
    end: str    # date field key


class CalendarSpec(BaseModel):
    """Month calendar: place each entity on its date."""

    date: str   # date field key
    title: str  # field key shown on the day


class DesignPlan(BaseModel):
    """A lightweight design proposal shown to the user BEFORE any code is written.

    The design worker produces this first (fast/cheap); the user reviews and
    revises it in plain language, and only on approval is it turned into a real
    HTML app (ViewManifest) by the heavier code step.
    """

    feature: str
    title: str
    summary: str = ""
    features: list[str] = Field(default_factory=list)  # bullet list of capabilities
    persistence: bool = False  # does it need to save data (tasks/memos) vs not (paint/calc)
    theme: str = "default"
    # Testable acceptance criteria the user approves with the plan; the Tester
    # verifies each one against the generated app (per-item ✅/❌).
    acceptance: list[str] = Field(default_factory=list)


class ViewManifest(BaseModel):
    feature: str                 # slug, e.g. "inventory"
    title: str                   # e.g. "在庫管理"
    description: str = ""         # 1-2 sentence plain explanation of what this does
    # data = structured standard components (form/list/charts...); app = real
    # generated HTML/JS/CSS rendered in a sandboxed iframe (interactive tools).
    kind: Literal["data", "app"] = "data"
    theme: str = "default"
    fields: list[FieldSpec] = Field(default_factory=list)
    list_columns: list[str] = Field(default_factory=list)
    stats: list[StatSpec] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    gantt: GanttSpec | None = None
    calendar: CalendarSpec | None = None
    html: str = ""               # kind="app": self-contained HTML for the sandboxed iframe
    # kind="app": agent-callable content operations the generated app implements via
    # window.applyAgentCommand(name, args). The feature worker maps a natural-language
    # instruction to one of these and the RUNNING app executes it (e.g. clear the
    # canvas, add an item, set a color) — so the worker edits content, not code.
    commands: list[dict] = Field(default_factory=list)  # [{name, description, params}]
    # Guidance generated together with commands so the Specialist Worker knows
    # what natural-language intents users are likely to express, which API each
    # maps to, and when to ask a clarifying question instead of guessing.
    worker_instructions: str = ""
    worker_examples: list[dict] = Field(default_factory=list)
    # Eval cases for the Specialist Worker: natural-language inputs and expected
    # behavior/state diff. Tester/Harness can use these to catch bad intent mapping.
    worker_eval_cases: list[dict] = Field(default_factory=list)
    clarification_policy: str = ""
    dangerous_action_policy: str = ""
    # How the Specialist Worker operates this app:
    # - commands: map NL to window.applyAgentCommand tools.
    # - state: edit the persisted AF.load/AF.save state directly.
    # - hybrid: prefer direct state edits for data changes, keep commands for
    #   UI-like actions that are safer to perform in the running iframe.
    worker_state_mode: Literal["commands", "state", "hybrid"] = "commands"
    # JSON Schema-like description of the persisted AF state. This lets the
    # Specialist Worker update unknown future data apps without hand-written APIs.
    state_schema: dict[str, Any] = Field(default_factory=dict)
    generated_by: str = "stub"   # gemini | claude-cli | stub


class EntityIn(BaseModel):
    project_id: str = "default"
    feature: str
    data: dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class Attachment(BaseModel):
    """A file/image attached to a feature-edit instruction (see reception.Attachment)."""

    name: str = ""
    mime: str = ""
    kind: Literal["image", "text"] = "text"
    content: str = ""


class EditIn(BaseModel):
    """A natural-language edit instruction for an existing feature (from its own
    worker chat on the feature screen)."""

    project_id: str = "default"
    text: str = Field(min_length=1, max_length=2000)
    attachments: list[Attachment] = Field(default_factory=list)


class StateIn(BaseModel):
    """Whole-app state blob persisted per feature for sandboxed generated apps.

    The generated app calls AF.save(state) (any JSON-able value) via a postMessage
    bridge; the frontend forwards it here so the app keeps its data across reloads
    without granting the sandbox localStorage/network access.
    """

    project_id: str = "default"
    state: Any = None
