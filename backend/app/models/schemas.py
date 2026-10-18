"""Pydantic models for API input. Stored documents are plain dicts (Mongo)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Exercise = Literal["squat", "pushup", "bicep_curl"]
CameraView = Literal["side", "front"]
Sex = Literal["male", "female", "prefer_not_to_say"]
Experience = Literal["beginner", "intermediate", "advanced"]
Goal = Literal["strength", "muscle_gain", "fat_loss", "general_fitness", "rehab_return"]
Equipment = Literal["bodyweight", "dumbbells", "barbell", "machines", "bands"]
SessionStatus = Literal["queued", "processing", "needs_reshoot", "ready_for_review", "approved", "failed"]

EXERCISES: tuple[str, ...] = ("squat", "pushup", "bicep_curl")
EXERCISE_LABELS = {"squat": "Squat", "pushup": "Push-up", "bicep_curl": "Bicep curl"}


class ClientCreate(BaseModel):
    """Coach creates the client; the client fills in the rest through their private link."""
    name: str = Field(min_length=1, max_length=80)
    coach_notes: Optional[str] = Field(default=None, max_length=2000)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    age: int = Field(ge=16, le=90)
    sex: Optional[Sex] = None
    height_cm: float = Field(ge=100, le=250)
    body_weight_kg: float = Field(ge=30, le=300)
    experience_level: Experience
    goal: Goal
    training_days_per_week: int = Field(ge=1, le=7)
    injuries_or_limits: Optional[str] = Field(default=None, max_length=500)
    equipment: list[Equipment] = Field(default_factory=list)
    timezone: str = "Asia/Colombo"
    consent: bool = False  # client has seen the privacy screen (video deleted, only numbers stored)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(v)
        except Exception as exc:
            raise ValueError("Unknown time zone") from exc
        return v


class ProfilePatch(BaseModel):
    """Coach edits: any profile field plus coach-only notes."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    age: Optional[int] = Field(default=None, ge=16, le=90)
    sex: Optional[Sex] = None
    height_cm: Optional[float] = Field(default=None, ge=100, le=250)
    body_weight_kg: Optional[float] = Field(default=None, ge=30, le=300)
    experience_level: Optional[Experience] = None
    goal: Optional[Goal] = None
    training_days_per_week: Optional[int] = Field(default=None, ge=1, le=7)
    injuries_or_limits: Optional[str] = Field(default=None, max_length=500)
    equipment: Optional[list[Equipment]] = None
    timezone: Optional[str] = None
    coach_notes: Optional[str] = Field(default=None, max_length=2000)


class VideoInputs(BaseModel):
    """Per-video form fields (section 2b)."""
    exercise: Exercise
    camera_view: CameraView
    load_kg: float = Field(default=0, ge=0, le=500)
    target_reps: Optional[int] = Field(default=None, ge=1, le=200)
    sets_done_today: Optional[int] = Field(default=None, ge=1, le=30)
    rpe: Optional[int] = Field(default=None, ge=1, le=10)
    pain_during_set: bool = False
    pain_text: Optional[str] = Field(default=None, max_length=300)
    body_weight_today_kg: Optional[float] = Field(default=None, ge=30, le=300)
    client_comment: Optional[str] = Field(default=None, max_length=500)


class ApproveIn(BaseModel):
    client_message: str = Field(min_length=1, max_length=2000)
    progress_message: Optional[str] = Field(default=None, max_length=2000)
    coach_note: Optional[str] = Field(default=None, max_length=2000)


class PlanApproveIn(BaseModel):
    plan: Optional[dict] = None   # coach-edited plan; if omitted the draft is approved as is


class LoginIn(BaseModel):
    password: str
