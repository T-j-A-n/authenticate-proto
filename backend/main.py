import uuid
import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from db import init_db, get_db, Session, Snapshot, KeystrokeWindow, GazeEvent, PasteEvent
import typenet_model
from keystroke_processor import KeystrokeProcessor
from runner import run_code
from evaluator import profile_complexity, check_quality, compute_scores
from integrity import compute_diff, compute_anomaly_score

import json as _json
import os
import numpy as np

app = FastAPI(title="AUTHENTICATE")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track keystroke processors for each session
_keystroke_processors = {}


@app.on_event("startup")
def startup():
    init_db()
    # Initialize TypeNet model
    typenet_model.get_model()


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
    
    # Convert keystroke sequences from 4-feature to 5-feature format
    converted_sequences = []
    for sequence in body.keystroke_sequences:
        converted_sequence = []
        for keystroke in sequence:
            converted_keystroke = KeystrokeProcessor.convert_keystroke_data(keystroke)
            converted_sequence.append(converted_keystroke)
        converted_sequences.append(converted_sequence)
    
    # Use real TypeNet model for enrollment
    baseline = typenet_model.enroll(converted_sequences)
    session.enrolled_embedding = json.dumps(baseline.tolist())
    db.commit()
    
    return {
        "success": True,
        "message": f"Enrolled with {len(body.keystroke_sequences)} keystroke windows"
    }


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


# ── Keystroke collection and continuous monitoring ─────────────────────────────

class KeystrokeBody(BaseModel):
    session_id: str
    hold_time_ms: float
    iki_kd_ms: float
    iki_ku_ms: float
    key_code: int


@app.post("/api/keystroke")
def add_keystroke(body: KeystrokeBody, db: DBSession = Depends(get_db)):
    """
    Add a single keystroke for enrollment or continuous monitoring.
    
    Enrollment phase: collect 100 keystrokes, then auto-enroll
    Monitoring phase: collect into 50-keystroke windows for anomaly detection
    """
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get or create keystroke processor for this session
    if body.session_id not in _keystroke_processors:
        _keystroke_processors[body.session_id] = KeystrokeProcessor()
    
    processor = _keystroke_processors[body.session_id]
    
    # Add keystroke and check status
    result = processor.add_keystroke(
        body.hold_time_ms,
        body.iki_kd_ms,
        body.iki_ku_ms,
        body.key_code
    )
    
    response = {
        "status": result['status'],
        "keystroke_count": result['keystroke_count'],
        "enrollment_complete": processor.enrollment_complete
    }
    
    # Check if enrollment is ready
    if result['status'] == 'enrollment_ready' and result['enrollment_windows']:
        # Auto-enroll with the collected windows (convert features)
        try:
            converted_windows = []
            for window in result['enrollment_windows']:
                converted_window = []
                for keystroke in window:
                    converted_keystroke = KeystrokeProcessor.convert_keystroke_data(keystroke)
                    converted_window.append(converted_keystroke)
                converted_windows.append(converted_window)
            
            baseline = typenet_model.enroll(converted_windows)
            session.enrolled_embedding = json.dumps(baseline.tolist())
            db.commit()
            response['message'] = 'Enrollment complete'
            response['enrollment_windows_count'] = len(result['enrollment_windows'])
        except Exception as e:
            response['error'] = str(e)
    
    # Check if we have a monitoring window ready
    if result['status'] == 'window_ready' and result['window']:
        if session.enrolled_embedding:
            baseline = np.array(json.loads(session.enrolled_embedding), dtype=np.float32)
            # Convert window features
            converted_window = []
            for keystroke in result['window']:
                converted_keystroke = KeystrokeProcessor.convert_keystroke_data(keystroke)
                converted_window.append(converted_keystroke)
            score = typenet_model.score_window(converted_window, baseline)
            threshold = 0.5
            is_suspicious = score < threshold
            
            response['monitoring'] = {
                'similarity_score': float(score),
                'is_suspicious': is_suspicious,
                'threshold': threshold
            }
    
    return response


class KeystrokeWindowBody(BaseModel):
    session_id: str
    window_data: list[list[float]]


@app.post("/api/keystroke-window")
def keystroke_window(body: KeystrokeWindowBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get baseline embedding
    if session.enrolled_embedding:
        baseline = np.array(json.loads(session.enrolled_embedding), dtype=np.float32)
    else:
        # No enrollment yet, return neutral score
        return {
            "similarity_score": 0.5,
            "is_suspicious": False,
            "message": "Enrollment not complete"
        }

    # Convert 4-feature keystroke data to 5-feature format
    converted_window = []
    for keystroke in body.window_data:
        converted_keystroke = KeystrokeProcessor.convert_keystroke_data(keystroke)
        converted_window.append(converted_keystroke)

    # Compute similarity using real TypeNet model
    score = typenet_model.score_window(converted_window, baseline)
    
    # Determine if suspicious (below threshold)
    threshold = 0.5  # Tunable threshold
    is_suspicious = score < threshold
    
    # Store window record
    kw = KeystrokeWindow(
        session_id=body.session_id,
        timestamp=datetime.utcnow(),
        similarity_score=score,
        window_data=json.dumps(body.window_data),
    )
    db.add(kw)
    db.commit()

    return {
        "similarity_score": score,
        "is_suspicious": is_suspicious,
        "threshold": threshold,
        "message": "suspicious activity detected" if is_suspicious else "activity normal"
    }


# ── Gaze events ───────────────────────────────────────────────────────────────

class GazeEventBody(BaseModel):
    session_id: str
    event_type: str
    event_data: dict
    timestamp: str


@app.post("/api/gaze-event")
def gaze_event(body: GazeEventBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Store gaze event
    gaze = GazeEvent(
        session_id=body.session_id,
        event_type=body.event_type,
        event_data=json.dumps(body.event_data),
    )
    db.add(gaze)
    db.commit()
    
    return {"success": True, "event_type": body.event_type}


# ── Paste events ──────────────────────────────────────────────────────────────

class PasteEventBody(BaseModel):
    session_id: str
    paste_length: int
    paste_content_preview: str
    paste_source: str
    timestamp: str


@app.post("/api/paste-event")
def paste_event(body: PasteEventBody, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Store paste event
    paste = PasteEvent(
        session_id=body.session_id,
        paste_length=body.paste_length,
        paste_content_preview=body.paste_content_preview,
        paste_source=body.paste_source,
    )
    db.add(paste)
    db.commit()
    
    return {"success": True, "paste_length": body.paste_length}


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
    gaze_events = (
        db.query(GazeEvent)
        .filter(GazeEvent.session_id == session_id)
        .order_by(GazeEvent.timestamp)
        .all()
    )
    paste_events = (
        db.query(PasteEvent)
        .filter(PasteEvent.session_id == session_id)
        .order_by(PasteEvent.timestamp)
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
        "gaze_events": [
            {
                "id": g.id,
                "timestamp": g.timestamp.isoformat(),
                "elapsed_seconds": int((g.timestamp - started).total_seconds()) if started else None,
                "event_type": g.event_type,
                "event_data": json.loads(g.event_data) if g.event_data else {},
            }
            for g in gaze_events
        ],
        "paste_events": [
            {
                "id": p.id,
                "timestamp": p.timestamp.isoformat(),
                "elapsed_seconds": int((p.timestamp - started).total_seconds()) if started else None,
                "paste_length": p.paste_length,
                "paste_content_preview": p.paste_content_preview,
                "paste_source": p.paste_source,
            }
            for p in paste_events
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
