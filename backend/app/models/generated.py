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


class ViewManifest(BaseModel):
    feature: str                 # slug, e.g. "inventory"
    title: str                   # e.g. "在庫管理"
    theme: str = "default"
    fields: list[FieldSpec] = Field(default_factory=list)
    list_columns: list[str] = Field(default_factory=list)
    stats: list[StatSpec] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    gantt: GanttSpec | None = None
    calendar: CalendarSpec | None = None
    generated_by: str = "stub"   # gemini | claude-cli | stub


class EntityIn(BaseModel):
    project_id: str = "default"
    feature: str
    data: dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
