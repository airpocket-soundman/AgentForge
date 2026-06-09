"""Models for AI-generated features (real self-expansion).

A generated feature = a `ViewManifest` (what the UI Designer worker produces) plus
schema-flexible entities stored via the generic CRUD. This is what makes adding an
arbitrary feature (e.g. a Gantt chart) actually work — no hand-written code per
feature.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FieldType = Literal["text", "textarea", "number", "date", "checkbox"]
ChartType = Literal["bar", "line", "pie", "doughnut"]


class FieldSpec(BaseModel):
    key: str
    label: str
    type: FieldType = "text"


class ChartSpec(BaseModel):
    """A standard chart component the renderer draws with Chart.js. The LLM only
    declares config (type + which fields) — no code is generated/executed."""

    type: ChartType = "bar"
    title: str = ""
    category: str  # field key used for labels (x / slice)
    value: str     # numeric field key used for values (summed per category)


class ViewManifest(BaseModel):
    feature: str                 # slug, e.g. "inventory"
    title: str                   # e.g. "在庫管理"
    theme: str = "default"
    fields: list[FieldSpec] = Field(default_factory=list)
    list_columns: list[str] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    generated_by: str = "stub"   # gemini | claude-cli | stub


class EntityIn(BaseModel):
    project_id: str = "default"
    feature: str
    data: dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
