"""
Seed script — creates two demo sessions.
Run: python seed.py  (with the backend NOT running, or using direct DB access)
"""

import json
import uuid
import random
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy.orm import Session as OrmSession

from db import init_db, SessionLocal, Session, Snapshot, KeystrokeWindow
from typenet_dummy import model as typenet_model
from integrity import compute_diff


CORRECT_CODE_A = '''\
class Stack:
    def __init__(self):
        self._data = []

    def push(self, item):
        self._data.append(item)

    def pop(self):
        if self.is_empty():
            raise IndexError("pop from empty stack")
        return self._data.pop()

    def peek(self):
        if self.is_empty():
            raise IndexError("peek from empty stack")
        return self._data[-1]

    def is_empty(self):
        return len(self._data) == 0

    def size(self):
        return len(self._data)
'''

CORRECT_CODE_B = '''\
class Stack:
    def __init__(self):
        self.items = []

    def push(self, item):
        self.items.append(item)

    def pop(self):
        if not self.items:
            raise IndexError("Stack is empty")
        return self.items.pop()

    def peek(self):
        if not self.items:
            raise IndexError("Stack is empty")
        return self.items[-1]

    def is_empty(self):
        return len(self.items) == 0

    def size(self):
        return len(self.items)
'''

JOURNAL_A = (
    "I plan to implement the Stack using a Python list as the underlying data structure. "
    "Push will use append(), pop will use list pop(), and peek will access index -1. "
    "I'll raise IndexError for empty stack operations. The list-based approach gives "
    "O(1) amortized time for push and pop since Python lists are dynamic arrays."
)

JOURNAL_B = (
    "I will implement a stack data structure using a linked list with nodes that point "
    "to the next element"
)

COMPREHENSION_A = {
    "0": (
        "Python lists use dynamic arrays under the hood. Appending to the end and popping "
        "from the end are both O(1) amortized because no shifting is required — we only "
        "touch the last element. The array only resizes occasionally, and that cost is "
        "amortized across many operations."
    ),
    "1": (
        "Two threads calling push() simultaneously could both read the current length, "
        "both decide to write to the same index, and one write would overwrite the other. "
        "To fix this I would use threading.Lock() and acquire it at the start of push and "
        "pop, releasing after the operation completes."
    ),
}

COMPREHENSION_B = {
    "0": "It works because lists are efficient in Python.",
    "1": "You would use locks or something like that to make it thread safe.",
}


def make_dummy_window(score_override: float = None) -> list[list[float]]:
    window = []
    for i in range(50):
        hold = random.uniform(80, 150)
        iki_kd = random.uniform(100, 200)
        iki_ku = random.uniform(50, 120)
        key_code = random.randint(65, 122)
        window.append([hold, iki_kd, iki_ku, float(key_code)])
    return window


def seed_student_a(db: OrmSession):
    session_id = "seed-student-a-" + str(uuid.uuid4())[:8]
    start = datetime.utcnow() - timedelta(hours=2)

    session = Session(
        id=session_id,
        student_id="student_001",
        problem_id="stack_001",
        enrolled_embedding=json.dumps(typenet_model.dummy_embedding.tolist()),
        approach_journal=JOURNAL_A,
        started_at=start,
        submitted_at=start + timedelta(minutes=44),
        submission_code=CORRECT_CODE_A,
        correctness_score=100.0,
        complexity_score=100.0,
        quality_score=92.0,
        robustness_score=100.0,
        comprehension_answers=json.dumps(COMPREHENSION_A),
        comprehension_score=9.0,
    )
    db.add(session)
    db.flush()

    # Build 30 snapshots incrementally over 45 minutes
    code_lines = CORRECT_CODE_A.splitlines()
    prev_code = ""
    num_snapshots = 30
    for i in range(num_snapshots):
        fraction = (i + 1) / num_snapshots
        lines_to_include = max(1, int(len(code_lines) * fraction))
        # Vary lines slightly to simulate realistic incremental typing
        lines_to_include = min(len(code_lines), lines_to_include + random.randint(-2, 3))
        lines_to_include = max(1, lines_to_include)
        current_code = "\n".join(code_lines[:lines_to_include])
        diff = compute_diff(prev_code, current_code)
        snap = Snapshot(
            session_id=session_id,
            timestamp=start + timedelta(minutes=45 * fraction),
            code=current_code,
            diff_lines=max(diff, random.randint(3, 8)),
            triggered_by="timer",
        )
        db.add(snap)
        prev_code = current_code

    # 40 keystroke windows, scores 0.78–0.92
    baseline = typenet_model.dummy_embedding
    for i in range(40):
        score = random.uniform(0.78, 0.92)
        kw = KeystrokeWindow(
            session_id=session_id,
            timestamp=start + timedelta(minutes=45 * (i + 1) / 40),
            similarity_score=score,
            window_data=json.dumps(make_dummy_window()),
        )
        db.add(kw)

    db.commit()
    print(f"Seeded Student A: session_id={session_id}")
    return session_id


def seed_student_b(db: OrmSession):
    session_id = "seed-student-b-" + str(uuid.uuid4())[:8]
    start = datetime.utcnow() - timedelta(hours=1, minutes=30)

    session = Session(
        id=session_id,
        student_id="student_002",
        problem_id="stack_001",
        enrolled_embedding=json.dumps(typenet_model.dummy_embedding.tolist()),
        approach_journal=JOURNAL_B,
        started_at=start,
        submitted_at=start + timedelta(minutes=10),
        submission_code=CORRECT_CODE_B,
        correctness_score=100.0,
        complexity_score=100.0,
        quality_score=78.0,
        robustness_score=100.0,
        comprehension_answers=json.dumps(COMPREHENSION_B),
        comprehension_score=3.0,
    )
    db.add(session)
    db.flush()

    # 3 snapshots: empty at 0min, 2 lines at 3min, 47+ lines at 8min
    snapshots_data = [
        (0, "class Stack:\n    pass", 2),
        (3, "class Stack:\n    def __init__(self):\n        self.items = []", 2),
        (8, CORRECT_CODE_B, 47),
    ]
    for minutes, code, diff in snapshots_data:
        snap = Snapshot(
            session_id=session_id,
            timestamp=start + timedelta(minutes=minutes),
            code=code,
            diff_lines=diff,
            triggered_by="timer",
        )
        db.add(snap)

    # 15 keystroke windows: first 5 normal (during journal), then drop to 0.31–0.52
    baseline = typenet_model.dummy_embedding
    for i in range(15):
        if i < 5:
            score = random.uniform(0.79, 0.85)
        else:
            score = random.uniform(0.31, 0.52)
        kw = KeystrokeWindow(
            session_id=session_id,
            timestamp=start + timedelta(minutes=10 * (i + 1) / 15),
            similarity_score=score,
            window_data=json.dumps(make_dummy_window()),
        )
        db.add(kw)

    db.commit()
    print(f"Seeded Student B: session_id={session_id}")
    return session_id


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        seed_student_a(db)
        seed_student_b(db)
        print("Seed complete.")
    finally:
        db.close()
