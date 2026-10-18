// Shapes returned by the RepCheck API (see backend/app/routers).

export type Exercise = "squat" | "pushup" | "bicep_curl";
export type Goal = "strength" | "muscle_gain" | "fat_loss" | "general_fitness" | "rehab_return";
export type Experience = "beginner" | "intermediate" | "advanced";
export type Equipment = "bodyweight" | "dumbbells" | "barbell" | "machines" | "bands";
export type SessionStatus =
  | "queued"
  | "processing"
  | "needs_reshoot"
  | "ready_for_review"
  | "approved"
  | "failed";
export type Trend = "improving" | "stable" | "declining" | "not_enough_data";

export interface Profile {
  name: string;
  age?: number;
  sex?: "male" | "female" | "prefer_not_to_say" | null;
  height_cm?: number;
  body_weight_kg?: number;
  experience_level?: Experience;
  goal?: Goal;
  training_days_per_week?: number;
  injuries_or_limits?: string | null;
  equipment?: Equipment[];
  timezone?: string;
}

export interface Warning {
  code: string;
  level: "red" | "amber" | "info";
  text: string;
}

export interface PlanSession {
  day: number;
  exercise: string;
  sets: number;
  reps: string;
  load_suggestion: string;
  load_change_pct: number;
  tempo: string;
  cue: string;
}
export interface WeekPlan {
  focus: string;
  sessions: PlanSession[];
  progression_rule: string;
  coach_review_points: string[];
}

export interface ClientReport {
  id: string;
  exercise: Exercise;
  created_at: string;
  form_score: number | null;
  rep_count: number | null;
  message: string | null;
  progress_message: string | null;
  approved_at: string;
}

export interface ClientHome {
  name: string;
  profile: Profile;
  profile_complete: boolean;
  consented: boolean;
  reports: ClientReport[];
  plan: WeekPlan | null;
  plan_week_start: string | null;
  weight_log: { date: string; kg: number }[];
  pending_count: number; // processed, waiting for the coach
  processing_count: number; // still being analysed
  reshoot_reason: string | null;
}

export interface CoachClientRow {
  id: string;
  name: string;
  goal?: Goal;
  experience_level?: Experience;
  last_session_at: string | null;
  latest_form_score: number | null;
  trend: Trend;
  session_count: number;
  warnings: Warning[];
}

export interface SeriesPoint {
  session_id: string;
  date: string;
  form_score: number | null;
  depth: number | null;
  eccentric_s: number | null;
  concentric_s: number | null;
  relative_load: number | null;
  load_kg: number | null;
  rep_count: number | null;
}

export interface SessionRow {
  id: string;
  exercise: Exercise;
  status: SessionStatus;
  created_at: string;
  form_score: number | null;
  rep_count: number | null;
  flags: string[];
  pain: boolean;
  load_kg: number | null;
  reshoot_reason: string | null;
}

export interface PlanDoc {
  id: string;
  week_start: string;
  draft: WeekPlan;
  approved: WeekPlan | null;
  status: "draft" | "approved";
  source: string;
  warnings: string[];
  max_load_increase_pct: number;
  conservative_mode: boolean;
  created_at: string;
}

export interface CoachClientDetail {
  id: string;
  name: string;
  link: string;
  profile: Profile;
  profile_complete: boolean;
  coach_notes: string | null;
  consent_at: string | null;
  derived: { bmi: { value: number; note: string } | null; femur_torso_ratio: number | null };
  warnings: Warning[];
  trend: Trend;
  weight_log: { date: string; kg: number }[];
  sessions: SessionRow[];
  series: Record<string, SeriesPoint[]>;
  plans: PlanDoc[];
}

export interface Flag {
  code: string;
  severity: "low" | "medium" | "high";
  reps: number[];
  evidence: string;
}

export interface RepMetrics {
  rep: number;
  depth_angle: number | null;
  range_of_motion: number;
  eccentric_s: number;
  concentric_s: number;
  bottom_pause_s: number;
  concentric_velocity: number;
  flags: string[];
  [key: string]: unknown;
}

export interface Judgement {
  exercise: Exercise;
  form_score: number | null;
  flags: Flag[];
  fatigue: { velocity_loss_pct: number | null; rpe: number | null; close_to_failure: boolean };
  relative_load: number | null;
  safety: { pain_reported: boolean; conservative_mode: boolean; reasons: string[] };
  progress_vs_last_3: {
    sessions_compared: number;
    form_score_change: number | null;
    depth_change_deg: number | null;
    relative_load_change: number | null;
  } | null;
  data_quality: { ok: boolean; notes: string[] };
  max_load_increase_pct: number;
  cue_limit: number;
  coach_attention: boolean;
}

export interface FeedbackDraft {
  summary: string;
  what_went_well: string[];
  fix_next_time: { cue: string; why: string; reps: number[] }[];
  coach_only_notes: string[];
  client_message: string;
}

export interface SessionDetail {
  id: string;
  client_id: string;
  exercise: Exercise;
  status: SessionStatus;
  created_at: string;
  inputs: {
    camera_view: string;
    load_kg: number;
    target_reps?: number | null;
    sets_done_today?: number | null;
    rpe?: number | null;
    pain_during_set: boolean;
    pain_text?: string | null;
    body_weight_today_kg?: number | null;
    client_comment?: string | null;
  };
  client: { id: string; name: string; goal?: Goal; experience_level?: Experience; age?: number; injuries_or_limits?: string | null };
  quality?: { ok: boolean; reason: string | null; notes: string[]; avg_visibility: number; full_body_pct: number };
  error?: string;
  reps?: RepMetrics[];
  set?: {
    rep_count: number;
    form_score: number | null;
    depth_mean: number | null;
    avg_eccentric_s: number | null;
    avg_concentric_s: number | null;
    tempo_cv: number | null;
    velocity_loss_pct: number | null;
    balance: { left_mean_min_deg: number; right_mean_min_deg: number; diff_deg: number; diff_pct: number } | null;
  };
  extras?: Record<string, unknown>;
  judgement?: Judgement;
  ai_feedback?: {
    draft: FeedbackDraft;
    source: string;
    warnings: string[];
    progress_draft: { trend: Trend; highlights: string[]; concerns: string[]; client_message: string };
    progress_source: string;
    model: string | null;
  };
  approved?: { client_message: string; progress_message: string | null; coach_note: string | null; approved_at: string } | null;
  overlay_available?: boolean;
}

// ---- GitHub-style dashboard ----
export interface ActivityDay {
  date: string;
  level: 0 | 1 | 2 | 3 | 4;
  points: number;
  exercises: Exercise[];
  reps: number;
  best_form: number | null;
}
export interface ExerciseCard {
  exercise: Exercise;
  label: string;
  color: string;
  sessions: number;
  best_form: number | null;
  sparkline: number[];
  last_date: string;
}
export interface FeedItem {
  date: string;
  type: "upload" | "best_depth" | "approved" | "streak";
  exercise: Exercise | null;
  text: string;
}
export interface FeedGroup {
  month: string;
  label: string;
  sessions: number;
  exercises: number;
  summary: string;
  items: FeedItem[];
}
export interface BadgeInfo {
  code: string;
  label: string;
  description: string;
  earned: boolean;
  earned_on: string | null;
}
export interface Activity {
  timezone: string;
  today: string;
  days: ActivityDay[];
  total_sets_last_year: number;
  streaks: { current: number; longest: number };
  totals: { sessions: number; reps: number; avg_form_30d: number | null; training_since: string | null; sets_last_year: number };
  thresholds: number[];
  exercise_cards: ExerciseCard[];
  feed: FeedGroup[];
  badges: BadgeInfo[];
  profile: { name: string; goal?: Goal; experience_level?: Experience };
}
