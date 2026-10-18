# RepCheck

AI helper for online personal trainers. Clients film a set; **MediaPipe** finds body points, **Python code** measures and judges form, and **Gemma** (open-weight, run locally with **Ollama**) turns only the numbers into feedback, a progress summary and a next-week plan. The **coach** reviews, edits and approves everything. The AI only drafts.

> Screenshot placeholder: `docs/screenshot-dashboard.png`, `docs/screenshot-review.png`, `docs/screenshot-heatmap.png`

## Run it (5 commands)

```bash
cp .env.example .env                         # set COACH_PASSWORD
docker compose up --build                    # backend, frontend, mongo, ollama (pulls Gemma)
docker compose exec backend python -m scripts.seed_demo_data   # 3 demo clients, ~1 year of data
# open http://localhost:3000/login  (coach)   and   http://localhost:3000/c/demo-kasun  (client)
```

No Docker? Quick local demo with an in-memory DB (no Ollama needed, template messages are used):

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Linux/Mac: .venv/bin/pip
python scripts/download_model.py
MONGODB_URI=mongomock:// DEMO_SEED_ON_START=true COACH_PASSWORD=demo uvicorn app.main:app --port 8000
cd ../frontend && npm install && BACKEND_URL=http://localhost:8000 npm run dev
```

Run the pose pipeline on any video: `python -m app.pose.cli clip.mp4 --exercise squat --view side`

## Tests

```bash
cd backend && pytest          # 126 tests: pose, judgement, LLM (mocked Ollama), activity maths, API (mongomock), seed
cd frontend && npm run typecheck && npm run build && npm test
```

## How it works

`video → MediaPipe PoseLandmarker → smoothing + quality → rep detection → per-rep metrics → rule-based judgement (profile + RPE + history) → Gemma explains the numbers → coach edits/approves → client sees it.` See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Limits (MVP)

- **Auth is minimal:** one coach password from env, signed cookie. Clients use unguessable private link tokens (anyone with the link has access). Not suitable for many coaches yet.
- Pose measurements come from a single phone camera: 2D-ish, sensitive to angle and light. Side view is recommended. Tested on synthetic skeletons and a blank video; **not validated on real lifting footage yet**.
- Three exercises only: squat, push-up, bicep curl. Thresholds are sensible defaults, not clinical standards.
- Not a medical tool. It never diagnoses, never gives diet advice, and routes pain / age 65+ / injuries to the coach.
- Ollama must be reachable from the backend (`OLLAMA_URL`). On Render, point it to your own machine or a GPU box.
- Jobs run in one in-process queue (no Celery). A restart re-queues videos still on disk.
- The overlay mp4 uses the `avc1` codec when OpenCV supports it, else `mp4v` (some browsers will not play `mp4v`).
- Demo data uses fixed, guessable tokens. Never seed a production database.

## Config

See [.env.example](.env.example): `MONGODB_URI`, `OLLAMA_URL`, `OLLAMA_MODEL`, `COACH_PASSWORD`, `ELEVENLABS_API_KEY` (optional, hides the voice button if empty), `FRONTEND_URL`, `MAX_UPLOAD_MB`. Deploy with [render.yaml](render.yaml).
