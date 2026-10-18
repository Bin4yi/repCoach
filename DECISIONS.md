# Decisions made without asking

One line of reason each.

## Repo and tooling
- Repo root is the project root (no extra `repcheck/` folder): simpler paths, and `git init` was requested in the working folder.
- Python venv at `backend/.venv` (git-ignored); Python 3.14 works with mediapipe 1.1.1, Dockerfile uses 3.12 for wider wheel support.
- `mongomock-motor` is a runtime dependency, because `MONGODB_URI=mongomock://` gives an in-memory demo mode.
- Frontend is Next 16 + React 19 + Tailwind 4 + Recharts 3; `typescript` pinned to ^5.9 for compatibility.
- Frontend calls `/api/*` on its own origin and Next rewrites it to the backend: first-party cookie, no CORS pain. `BACKEND_URL` must exist at **build** time (rewrites are baked in). `NEXT_PUBLIC_API_URL` allows direct calls.
- `proxyClientMaxBodySize: 110mb` so 100 MB videos pass through the Next proxy.
- Git commits use a placeholder author name "RepCheck Dev" with your email; change with `git config` if you prefer.

## Pose and measurement
- Landmarks use image-plane coordinates (x scaled by aspect ratio) for view detection and world landmarks for angles when present. Assumes world-landmark y points down like the image (not verified on real footage).
- `num_poses=2` so a second person can be detected; we follow the person with the biggest body box.
- Videos over 30 fps use every 2nd frame; frames are downscaled to 640 px.
- Smoothing: visibility < 0.5 dropped, gaps up to 5 frames interpolated, Savitzky-Golay (0.25 s window, order 2).
- Reps = valleys of the main signal (knee/elbow angle; front-view squat uses relative hip height) via `scipy.signal.find_peaks` with prominence and min spacing. Rep start/end = within 10% of the top level.
- A flag needs at least 25% of reps affected (and 1 rep). Severity: >=70% high, >=30% medium, else low. Fatigue-depth flag is always medium.
- Squat lean limit 45 deg, adjusted by femur/torso ratio (+60 deg per 1.0 above 0.9, capped at +-10 deg) so long-femur lifters are not over-corrected.
- Beginners get +10 deg depth slack, a 0.8 s (not 1.0 s) minimum descent, and 2 cues max (others 3).
- Velocity loss = first vs last reps' lifting speed (needs 4+ reps), a proxy in deg/s, not bar speed.
- "Close to failure" = RPE >= 8 and velocity loss >= 20%.
- Quality gate: needs reshoot if a person is seen in <60% of frames, full body in <60%, >30% frames with 2 people, the camera view disagrees with the chosen one (shoulder width/torso ratio 0.45), or no reps are found.
- Overlay: `avc1` codec first, `mp4v` fallback. Overlay shows red skeleton on flagged reps.
- On this Windows machine the first import of scipy once failed with an "Application Control policy" DLL block, then worked on retry. It is an environment quirk, not a code issue.

## Form score weights (0-100, computed in code)
Start at 100, subtract `weight x (0.4 + 0.6 x share of reps flagged) x severity multiplier` (low 0.6, medium 0.85, high 1.0).
Weights: shallow_depth 20, knee_cave 20, partial_range 20, excess_forward_lean 15, hip_sag 15, body_swing 15, elbow_drift 12, depth_drops_with_fatigue 10, hips_high 10, no_lockout 10, rushed_eccentric 8.
Plus up to 8 points for uneven tempo (CV 0.5 = full penalty) and up to 6 for left/right difference (15% = full).

## Judgement and safety
- Conservative mode if pain, age >= 65, an injury note that keywords-match the exercise (knee/hip/back for squat, etc.), goal rehab_return, or poor video quality. Keyword matching is a convenience, not diagnosis.
- Max weekly load increase 5%; 0% in conservative mode or if any of the last 3 sessions had pain. Deload floor -20%.
- Added `load_change_pct` to the plan schema so the cap can be enforced numerically; the human-readable `load_suggestion` is rewritten by code from the clamped value (rounded DOWN to 0.5 kg).
- Coach edits to a plan are re-clamped on approval (same cap, supported exercises, sessions <= training days).
- Number check: every number in LLM text must be within 0.5 of a number in the input data. Strict on purpose; failing twice falls back to a plain template (the coach sees "Template").
- Also rejected: diet/calorie words, messages over 120 words, suggesting extra load after pain. Pain messages are forced to say "stop" and "coach". Coach-only notes about pain/safety are always written by code, never by the model.
- Progress `trend` comes from code (slope of last 6 form scores, +-5 points) and overrides the model.
- LLM payload has no name; the model says "the client". Coach notes and BMI are never sent.
- Default model `gemma3:4b`; if it is not installed, the backend switches to the newest installed Gemma tag.
- Added statuses beyond the spec: `failed` (server problem, e.g. pose model missing) so it is not confused with a re-shoot.

## Data and API
- Documents use string UUID ids; Mongo client is `tz_aware`. Raw video is deleted in a `finally` block after processing; overlay is deleted on approval or after 7 days (sweep at startup).
- Client home endpoint returns approved reports only; coach notes and BMI are coach-only.
- Time-zone: stored on the client profile, default Asia/Colombo; the activity endpoint buckets days in that zone.
- Heatmap levels: quartiles of the client's own non-zero days (as GitHub does); the best day is always level 4 so beginners with few days still see dark squares. Points = sets x reps (+5 if form >= 80). Sessions that need a reshoot or are not processed do not count.
- Streak = calendar days in a run. A rest day does not break it while the rest days in any 7-day window stay within `7 - training_days_per_week`. A streak ends on its last training day; today without training is not yet a break.
- Demo seed uses the real pipeline on synthetic skeletons (about 20 s). Fixed demo tokens, labelled `demo`.
- Upload: video length is checked with OpenCV when it can read the file; unreadable files become "needs reshoot" in the worker.
- ElevenLabs voice: TTS of the coach's message text, button shown only when `ELEVENLABS_API_KEY` is set.
- Queue is one asyncio worker; tests run jobs inline.
