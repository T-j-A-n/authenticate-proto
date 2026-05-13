# AUTHENTICATE — Prototype

A coding assessment platform with keystroke biometric integrity checking. Students solve problems in a browser-based editor while keystroke timing is captured and scored against a biometric baseline. Instructors see a dashboard with session timelines, commit diffs, and anomaly flags.

---

## Quick Start

**Terminal 1 — backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Terminal 2 — frontend**
```bash
cd frontend
npm install
npm run dev
```

Then open:
- **Student view** → http://localhost:5173/student
- **Instructor view** → http://localhost:5173/instructor

To pre-populate the instructor dashboard with demo data:
```bash
cd backend
python seed.py
```

> Run `seed.py` once, after the backend has started for the first time (it needs the database to exist).

---

## How It Works

### Student flow

1. **Approach journal** — The editor is locked until the student submits a written plan (≥100 characters). This is saved to the database and shown in the instructor timeline.
2. **Coding** — Monaco Editor (same engine as VS Code) with Python syntax highlighting. Every 60 seconds the full editor content is snapshotted automatically. Running tests also triggers a snapshot.
3. **Keystroke capture** — Every keystroke fires `keydown`/`keyup` events. Each event records hold time, inter-key intervals, and key code. When the buffer reaches 50 keystrokes, a window is sent to the backend and scored against the enrolled biometric baseline. The score appears as a coloured badge (green/amber/red) in the editor header.
4. **Run tests** — Posts the current code to `/api/run`. Only the visible tests run. Results appear inline below the editor.
5. **Submit** — Posts to `/api/submit`. Runs all tests (visible + hidden), profiles complexity, and lints the code. Transitions to the comprehension check.
6. **Comprehension check** — Two randomly selected questions from the problem definition. 10-minute countdown. Answers are stored for instructor review.

### Instructor flow

1. **Cohort table** — Lists all sessions with aggregated score, anomaly window count, maximum single-diff size, and comprehension score. Rows with ≥3 anomaly windows are highlighted amber. Sorted by anomaly count descending by default. Any column header is clickable to re-sort.
2. **Session timeline** — Click any row to expand:
   - **Confidence curve** — SVG chart of biometric similarity scores over time. Dashed threshold line at 0.6. Shaded area below threshold. Red vertical markers where a single snapshot added ≥20 lines.
   - **Commit log** — Chronological list of snapshots. Each entry shows elapsed time, lines added, and trigger (timer or test run). Snapshots with ≥20 lines are highlighted amber. Click "Show diff" to expand an inline diff.
   - **Comprehension answers** — The student's written answers alongside the question text. Input field for the instructor to enter a score (0–10), which is saved via PATCH.

---

## Directory Structure

```
authenticate-proto/
├── backend/
│   ├── main.py            # FastAPI app — all routes
│   ├── db.py              # SQLAlchemy models + SQLite setup
│   ├── runner.py          # Subprocess code execution with timeout
│   ├── evaluator.py       # Test runner, complexity profiler, linter
│   ├── typenet_dummy.py   # Biometric model placeholder
│   ├── integrity.py       # Diff computation + anomaly scoring
│   ├── seed.py            # Seeds two demo sessions
│   ├── problems/
│   │   └── stack_001.json # Problem definition
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── main.jsx           # React entry point
    │   ├── App.jsx            # Router: /student and /instructor
    │   ├── api.js             # Shared axios instance (baseURL: localhost:8000)
    │   ├── StudentView.jsx    # Full student UI
    │   ├── InstructorView.jsx # Cohort table + session timeline
    │   ├── KeystrokeCapture.js # Keystroke event capture + windowed POST
    │   └── ConfidenceCurve.jsx # SVG biometric score chart
    ├── index.html
    ├── package.json
    └── vite.config.js
```

---

## Backend

### `main.py` — API routes

All routes live in one file. FastAPI with SQLAlchemy dependency injection.

| Method | Route | What it does |
|--------|-------|--------------|
| GET | `/api/health` | Liveness check |
| POST | `/api/sessions` | Create a new session, returns UUID |
| GET | `/api/sessions/{id}` | Fetch a single session |
| GET | `/api/sessions` | List all sessions |
| POST | `/api/enroll` | Compute + store biometric baseline from keystroke sequences |
| GET | `/api/problems/{id}` | Load problem JSON from `problems/` |
| POST | `/api/run` | Run visible tests, save snapshot |
| POST | `/api/submit` | Run all tests, profile complexity, lint, save scores |
| POST | `/api/snapshot` | Save a timed snapshot of editor content |
| POST | `/api/keystroke-window` | Score a 50-keystroke window, store result |
| POST | `/api/journal` | Save approach journal text |
| POST | `/api/comprehension` | Save comprehension answers |
| GET | `/api/instructor/cohort` | Aggregated stats for all sessions |
| GET | `/api/instructor/session/{id}/timeline` | Full session timeline |
| PATCH | `/api/instructor/session/{id}/comprehension-score` | Set instructor score |

CORS is open to all origins (`*`) — this is intentional for the prototype so the frontend works regardless of how it is served.

### `db.py` — Database

SQLite via SQLAlchemy ORM. The database file `authenticate.db` is created automatically in the `backend/` directory on first startup.

**Three tables:**

- **sessions** — one row per student session. Stores journal, submitted code, all four scores, comprehension answers, enrolled biometric embedding.
- **snapshots** — append-only record of editor state over time. Each row has the full code, computed diff line count, and whether it was triggered by the timer or a test run.
- **keystroke_windows** — one row per 50-keystroke window scored. Stores the similarity score and the raw feature array.

### `runner.py` — Code execution

Writes the student's code + a test harness to a temp file, runs it with `subprocess.run` and a 5-second timeout, parses `TEST:name:PASS/FAIL:detail` lines from stdout. Exception-expecting tests (e.g. `IndexError`) are handled as a special case in the harness.

### `evaluator.py` — Scoring

- **Complexity profiling** — runs the student's code at n=100, 1000, 10000, times each run, fits the growth curve to O(1)/O(log n)/O(n)/O(n log n)/O(n²)/O(n³).
- **Quality check** — runs `pylint` via subprocess, extracts the numeric score, counts functions and max function length.
- **Score weighting** — correctness 40%, complexity 20%, quality 20%, robustness 10%, process 10% (manual).

### `typenet_dummy.py` — Biometric model

Placeholder for a real TypeNet LSTM. The interface is fixed so only this file needs to change when a trained model is available:

- `enroll(sequences) → np.ndarray` — averages embeddings from multiple keystroke windows into a baseline.
- `score_window(window, baseline) → float` — cosine similarity between a new window's embedding and the baseline. Returns ~0.85 ± 0.05 with small random noise so the confidence curve looks alive.

The dummy adds noise so the demo curve oscillates realistically instead of showing a flat line. The seeded suspicious session has manually injected low scores (0.31–0.52) to simulate a real anomaly.

### `integrity.py` — Diff + anomaly logic

- `compute_diff` — `difflib.unified_diff`, counts lines beginning with `+` (excluding the `+++` header).
- `compute_anomaly_score` — counts windows below 0.6, finds max single diff, computes time-to-first-code. Flags a session if anomaly count ≥3 or max diff ≥50.

### `seed.py` — Demo data

Creates two sessions directly in the database (no HTTP):

- **student_001 (clean)** — 30 incremental snapshots over 45 minutes, 40 keystroke windows all scoring 0.78–0.92, detailed comprehension answers, linter score 9.2.
- **student_002 (suspicious)** — 3 snapshots (empty → 2 lines → 47 lines in one go at minute 8), 15 keystroke windows where scores drop from 0.79–0.85 to 0.31–0.52, vague comprehension answers. Approach journal says "linked list" but the submitted code uses a Python list — intentional mismatch.

### `problems/stack_001.json`

Defines the problem shown to students. Fields:
- `title`, `description`, `starter_code`, `language`
- `visible_tests` — shown to the student, run on every "Run tests" click
- `hidden_tests` — run only on submission, used for robustness score
- `expected_complexity` — used to grade the complexity score
- `docs_allowlist` — domains the documentation iframe is allowed to load
- `comprehension_questions` — pool of questions; 2 are picked randomly at submission

---

## Frontend

### `api.js`

A single axios instance with `baseURL: 'http://localhost:8000'`. All components import from here so the backend URL is defined in one place.

### `App.jsx`

React Router with two routes: `/student` → `StudentView`, `/instructor` → `InstructorView`. Visiting any other path redirects to `/student`.

### `StudentView.jsx`

Manages the full student lifecycle through four stages:

| Stage | What the student sees |
|-------|-----------------------|
| `journal` | Problem statement + approach journal textarea with character counter. Editor is hidden. |
| `coding` | Three-column layout: problem + journal (left), editor + test results (centre), docs iframe (right). |
| `comprehension` | Two questions with textareas and a 10-minute countdown. |
| `done` | Confirmation screen with final scores. |

On mount, it simultaneously creates a session (`POST /api/sessions`) and fetches the problem (`GET /api/problems/stack_001`). If either fails, an error banner explains why.

The auto-snapshot interval (`setInterval`, 60s) is tied to the `coding` stage and cleaned up on unmount or stage change.

### `KeystrokeCapture.js`

Attaches `keydown`/`keyup` listeners to the Monaco Editor container. Maintains a rolling buffer of feature vectors `[hold_time_ms, iki_kd_ms, iki_ku_ms, key_code]`. Every 10 keystrokes, if the buffer has ≥50 entries, the last 50 are posted to `/api/keystroke-window`. The returned similarity score is passed to a callback which updates the confidence badge in the UI.

### `ConfidenceCurve.jsx`

Pure SVG chart. Takes `windows` (keystroke window scores) and `snapshots` (for large-diff markers) as props. Renders:
- A polyline of similarity scores over elapsed time
- Coloured dots per point (green ≥0.7, amber ≥0.5, red <0.5)
- A dashed threshold line at 0.6 with a shaded area below it
- Red dashed vertical markers at snapshots with ≥20 changed lines

### `InstructorView.jsx`

Polls `/api/instructor/cohort` every 10 seconds so live sessions appear automatically. Clicking a row fetches the full timeline and renders the confidence curve, commit log with expandable diffs, and the comprehension scoring input.

---

## Swapping in the Real Biometric Model

When a trained TypeNet checkpoint is ready, replace `backend/typenet_dummy.py` with a file that:

1. Loads the PyTorch LSTM checkpoint in `__init__`
2. Runs a `torch.no_grad()` forward pass in `get_embedding`
3. Keeps `enroll(sequences)` and `score_window(window, baseline)` signatures identical

No other file needs to change.

---

## Known Limitations (by design)

- No real TypeNet model — dummy returns a constant + small noise
- No sandboxed execution environment — subprocess with 5s timeout only
- No user authentication — `student_id` is a random string generated client-side
- No concurrent write safety — SQLite is single-writer
- No automated comprehension scoring — instructor enters score manually
- Documentation iframe is sandbox-only, not network-restricted
