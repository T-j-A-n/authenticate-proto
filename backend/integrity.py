import difflib
from datetime import datetime


def compute_diff(previous_code: str, current_code: str) -> int:
    diff = difflib.unified_diff(
        previous_code.splitlines(),
        current_code.splitlines(),
        lineterm="",
    )
    count = 0
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            count += 1
    return count


def compute_anomaly_score(session_id: str, db) -> dict:
    from db import KeystrokeWindow, Snapshot, Session as DBSession

    session = db.query(DBSession).filter(DBSession.id == session_id).first()
    windows = db.query(KeystrokeWindow).filter(KeystrokeWindow.session_id == session_id).all()
    snapshots = db.query(Snapshot).filter(Snapshot.session_id == session_id).order_by(Snapshot.timestamp).all()

    anomaly_window_count = sum(1 for w in windows if w.similarity_score < 0.6)
    max_single_diff = max((s.diff_lines for s in snapshots), default=0)

    time_to_first_code = None
    if session and snapshots:
        for snap in snapshots:
            non_empty = sum(1 for line in snap.code.splitlines() if line.strip())
            if non_empty > 5:
                delta = snap.timestamp - session.started_at
                time_to_first_code = int(delta.total_seconds())
                break

    flagged = anomaly_window_count >= 3 or max_single_diff >= 50

    return {
        "anomaly_window_count": anomaly_window_count,
        "max_single_diff": max_single_diff,
        "time_to_first_code_seconds": time_to_first_code,
        "flagged": flagged,
    }
