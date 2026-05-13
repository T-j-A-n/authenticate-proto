import uuid
import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from db import init_db, get_db, Session, Snapshot, KeystrokeWindow
import typenet_dummy
from runner import run_code
from evaluator import profile_complexity, check_quality, compute_scores
from integrity import compute_diff, compute_anomaly_score

import json as _json
import os

app = FastAPI(title="AUTHENTICATE")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


PROBLEMS_DIR = os.path.join(os.path.dirname(__file__), "problems")


def load_problem(problem_id: str) -> dict:
    path = os.path.join(PROBLEMS_DIR, f"{problem_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Problem not found")
    with open(path) as f:
        return json.load(f)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Session management ────────────────────────────────────────────────────────

class CreateSessionBody(BaseModel):
    student_id: str
    problem_id: str


@app.post("/api/sessions")
def create_session(body: CreateSessionBody, db: DBSession = Depends(get_db)):
    session = Session(
        id=str(uuid.uuid4()),
        student_id=body.student_id,
        problem_id=body.problem_id,
        started_at=datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_to_dict(session)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_dict(session)


@app.get("/api/sessions")
def list_sessions(db: DBSession = Depends(get_db)):
    sessions = db.query(Session).all()
    return [_session_to_dict(s) for s in sessions]


def _session_to_dict(s: Session) -> dict:
    return {
        "id": s.id,
        "student_id": s.student_id,
        "problem_id": s.problem_id,
        "enrolled_embedding": s.enrolled_embedding,
        "approach_journal": s.approach_journal,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        "submission_code": s.submission_code,
        "correctness_score": s.correctness_score,
        "complexity_score": s.complexity_score,
        "quality_score": s.quality_score,
        "robustness_score": s.robustness_score,
        "comprehension_answers": s.comprehension_answers,
        "comprehension_score": s.comprehension_score,
    }


# ── Enrollment ────────────────────────────────────────────────────────────────

class EnrollBody(BaseModel):
    session_id: str
    keystroke_sequences: list[list[list[float]]]


@app.post("/api/enroll")
def enroll(body: EnrollBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    baseline = typenet_dummy.enroll(body.keystroke_sequences)
    session.enrolled_embedding = json.dumps(baseline.tolist())
    db.commit()
    return {"success": True}


# ── Problem ───────────────────────────────────────────────────────────────────

@app.get("/api/problems/{problem_id}")
def get_problem(problem_id: str):
    return load_problem(problem_id)


# ── Code execution ────────────────────────────────────────────────────────────

class RunBody(BaseModel):
    session_id: str
    code: str


@app.post("/api/run")
def run(body: RunBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    problem = load_problem(session.problem_id)
    result = run_code(body.code, problem["visible_tests"])

    _save_snapshot(body.session_id, body.code, "run", db)

    return result


class SubmitBody(BaseModel):
    session_id: str
    code: str


@app.post("/api/submit")
def submit(body: SubmitBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    problem = load_problem(session.problem_id)

    visible_results = run_code(body.code, problem["visible_tests"])
    hidden_results = run_code(body.code, problem["hidden_tests"])
    complexity_class = profile_complexity(body.code, problem)
    quality = check_quality(body.code)
    scores = compute_scores(
        visible_results["results"],
        hidden_results["results"],
        complexity_class,
        problem["expected_complexity"],
        quality,
    )

    session.submission_code = body.code
    session.submitted_at = datetime.utcnow()
    session.correctness_score = scores["correctness_score"]
    session.complexity_score = scores["complexity_score"]
    session.quality_score = scores["quality_score"]
    session.robustness_score = scores["robustness_score"]
    db.commit()

    _save_snapshot(body.session_id, body.code, "run", db)

    return {
        "visible_results": visible_results["results"],
        "hidden_results": hidden_results["results"],
        "complexity_class": complexity_class,
        "quality": quality,
        "scores": scores,
    }


def _save_snapshot(session_id: str, code: str, triggered_by: str, db: DBSession):
    last = (
        db.query(Snapshot)
        .filter(Snapshot.session_id == session_id)
        .order_by(Snapshot.timestamp.desc())
        .first()
    )
    diff = compute_diff(last.code if last else "", code)
    snap = Snapshot(
        session_id=session_id,
        timestamp=datetime.utcnow(),
        code=code,
        diff_lines=diff,
        triggered_by=triggered_by,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


# ── Integrity ─────────────────────────────────────────────────────────────────

class SnapshotBody(BaseModel):
    session_id: str
    code: str


@app.post("/api/snapshot")
def snapshot(body: SnapshotBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    snap = _save_snapshot(body.session_id, body.code, "timer", db)
    return {"snapshot_id": snap.id, "diff_lines": snap.diff_lines}


class KeystrokeWindowBody(BaseModel):
    session_id: str
    window_data: list[list[float]]


@app.post("/api/keystroke-window")
def keystroke_window(body: KeystrokeWindowBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.enrolled_embedding:
        import numpy as np
        baseline = np.array(json.loads(session.enrolled_embedding), dtype=np.float32)
    else:
        import numpy as np
        baseline = typenet_dummy.model.dummy_embedding

    score = typenet_dummy.score_window(body.window_data, baseline)

    kw = KeystrokeWindow(
        session_id=body.session_id,
        timestamp=datetime.utcnow(),
        similarity_score=score,
        window_data=json.dumps(body.window_data),
    )
    db.add(kw)
    db.commit()

    return {"similarity_score": score}


# ── Approach journal ──────────────────────────────────────────────────────────

class JournalBody(BaseModel):
    session_id: str
    text: str


@app.post("/api/journal")
def journal(body: JournalBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.approach_journal = body.text
    db.commit()
    return {"success": True}


# ── Comprehension ─────────────────────────────────────────────────────────────

class ComprehensionBody(BaseModel):
    session_id: str
    answers: dict


@app.post("/api/comprehension")
def comprehension(body: ComprehensionBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.comprehension_answers = json.dumps(body.answers)
    db.commit()
    return {"success": True}


# ── Instructor ────────────────────────────────────────────────────────────────

@app.get("/api/instructor/cohort")
def cohort(db: DBSession = Depends(get_db)):
    sessions = db.query(Session).all()
    result = []
    for s in sessions:
        windows = db.query(KeystrokeWindow).filter(KeystrokeWindow.session_id == s.id).all()
        snapshots = db.query(Snapshot).filter(Snapshot.session_id == s.id).all()
        anomaly_count = sum(1 for w in windows if w.similarity_score < 0.6)
        max_diff = max((snap.diff_lines for snap in snapshots), default=0)
        total = None
        if s.correctness_score is not None:
            total = round(
                (s.correctness_score or 0) * 0.4
                + (s.complexity_score or 0) * 0.2
                + (s.quality_score or 0) * 0.2
                + (s.robustness_score or 0) * 0.1,
                1,
            )
        result.append({
            "session_id": s.id,
            "student_id": s.student_id,
            "total_score": total,
            "anomaly_count": anomaly_count,
            "max_diff_lines": max_diff,
            "comprehension_score": s.comprehension_score,
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            "flagged": anomaly_count >= 3 or max_diff >= 50,
        })
    return result


@app.get("/api/instructor/session/{session_id}/timeline")
def timeline(session_id: str, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    snapshots = (
        db.query(Snapshot)
        .filter(Snapshot.session_id == session_id)
        .order_by(Snapshot.timestamp)
        .all()
    )
    windows = (
        db.query(KeystrokeWindow)
        .filter(KeystrokeWindow.session_id == session_id)
        .order_by(KeystrokeWindow.timestamp)
        .all()
    )

    started = session.started_at

    return {
        "session": _session_to_dict(session),
        "snapshots": [
            {
                "id": s.id,
                "timestamp": s.timestamp.isoformat(),
                "elapsed_seconds": int((s.timestamp - started).total_seconds()) if started else None,
                "code": s.code,
                "diff_lines": s.diff_lines,
                "triggered_by": s.triggered_by,
            }
            for s in snapshots
        ],
        "keystroke_windows": [
            {
                "id": w.id,
                "timestamp": w.timestamp.isoformat(),
                "elapsed_seconds": int((w.timestamp - started).total_seconds()) if started else None,
                "similarity_score": w.similarity_score,
            }
            for w in windows
        ],
        "approach_journal": session.approach_journal,
        "comprehension_answers": json.loads(session.comprehension_answers) if session.comprehension_answers else None,
    }


class ComprehensionScoreBody(BaseModel):
    score: float


@app.patch("/api/instructor/session/{session_id}/comprehension-score")
def set_comprehension_score(session_id: str, body: ComprehensionScoreBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.comprehension_score = body.score
    db.commit()
    return {"success": True}
