"""Structured-output schemas for the three Gemma tasks (Pydantic models -> JSON schema for Ollama)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Cue(BaseModel):
    cue: str
    why: str
    reps: list[int] = Field(default_factory=list)


class SessionFeedback(BaseModel):
    summary: str
    what_went_well: list[str]
    fix_next_time: list[Cue]
    coach_only_notes: list[str]
    client_message: str


class ProgressSummary(BaseModel):
    trend: Literal["improving", "stable", "declining", "not_enough_data"]
    highlights: list[str]
    concerns: list[str]
    client_message: str


class PlanSession(BaseModel):
    day: int = Field(ge=1, le=7)
    exercise: str
    sets: int = Field(ge=1, le=10)
    reps: str
    load_suggestion: str
    # Added to the spec'd schema so the weekly load change can be validated and clamped in code.
    load_change_pct: float = 0.0
    tempo: str
    cue: str


class WeekPlan(BaseModel):
    focus: str
    sessions: list[PlanSession]
    progression_rule: str
    coach_review_points: list[str]


def _inline(node, defs):
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline(defs[node["$ref"].split("/")[-1]], defs)
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(x, defs) for x in node]
    return node


def json_schema(model: type[BaseModel]) -> dict:
    """JSON schema with $refs inlined (the simplest form for Ollama's grammar-constrained output)."""
    schema = model.model_json_schema()
    return _inline(schema, schema.get("$defs", {}))
