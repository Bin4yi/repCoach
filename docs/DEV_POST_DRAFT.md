---
title: RepCheck: an open-weight AI assistant for online personal trainers
tags: devchallenge, hacktoberfest, ai, gemma
---

## What I Built

Online coaches check dozens of workout videos a week. It takes long, and the feedback is often just "looks good". **RepCheck** measures every rep for them. A client films a set. Software counts reps and measures depth, tempo, balance and fatigue. Gemma, an open-weight model running on the coach's own machine, writes a draft: feedback for the video, a progress summary, and a plan for next week. The coach edits and approves it before the client sees anything.

**Who pays:** online coaches with 20 to 100 clients. **Price idea:** about $10 per month per coach seat for up to 20 clients, then $0.50 per extra client. (TODO: validate with real coaches.)

## Demo

- Video: _TODO link_
- Screenshots: _TODO coach dashboard, session review, GitHub-style training heatmap_

## Code

_TODO: GitHub link_

## How I Built It

**MediaPipe measures. Code judges. Gemma explains.**

1. MediaPipe Pose finds 33 body points in each frame.
2. Python smooths them, counts reps, and computes angles, depth, tempo, velocity loss and left/right balance. A form score from 0 to 100 comes from simple weighted rules, not from the LLM.
3. A judgement layer combines the numbers with the client profile (age, goal, experience, injuries), the RPE and the history. It decides what is safe: pain, age 65+, injuries or poor video quality switch on a careful mode with no load increases.
4. Gemma only receives the numbers, never the video and never the client's name. Its output must be valid JSON, every number in its text must exist in the data, and load changes in plans are clamped in code. If checks fail twice, a plain template is used.
5. The coach reviews everything in a dashboard (overlay video, per-rep table, flags, editable draft) and approves.

Why the LLM never sees the video: it is cheaper, it is private, and it cannot invent a knee angle it never saw. A language model is good at explaining. A pose model plus code is good at measuring.

Clients also get a GitHub-style training page: contribution heatmap, streaks, exercise cards, activity feed and badges, all computed in code.

Stack: Python, FastAPI, MediaPipe Tasks, OpenCV, NumPy/SciPy, Ollama + Gemma, MongoDB Atlas, Next.js, Recharts, Render. Optional ElevenLabs voice notes.

## Why Does Open Innovation Matter?

- **Privacy of body videos.** Videos are processed locally and deleted. Only numbers are stored.
- **Near-zero cost per video.** Local Gemma reads a few hundred numbers instead of a video, so a $10 per month price can work.
- **No lock-in.** Swap the model by changing `OLLAMA_MODEL`.
- **Accuracy by splitting jobs.** Measuring and explaining are separate, so the model cannot hallucinate measurements.

Cost per video (estimates only. TODO: check current prices before publishing):

| Approach | What is sent | Rough cost per video |
|---|---|---|
| Closed vision API reading frames | about 60 to 100 frames as images | TODO (guess: $0.05 to $0.30) |
| RepCheck: MediaPipe + local Gemma reading numbers | about 1 to 2 KB of text | about $0 API cost (electricity / GPU box only) |

## My First User

_TODO. Questions to ask a real trainer:_
1. How many videos do you review per week, and how long does each take?
2. What do you tell clients most often about form?
3. Would you trust a draft you can edit? What would make you stop trusting it?
4. What would you pay per month? Per client?
5. Which exercises do you need next?
6. Is the pain / age / injury handling what you would expect?

## Prize Categories

- **Gemma:** the writing layer (feedback, progress, plan) is Gemma through Ollama with structured JSON output.
- **MongoDB Atlas:** clients, sessions, weight log and plans live in Atlas (`MONGODB_URI`).
- **Render:** `render.yaml` deploys the backend and frontend.
- **ElevenLabs (optional):** the coach can turn the approved message into a voice note.
