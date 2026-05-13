from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./authenticate.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    student_id = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    enrolled_embedding = Column(Text, nullable=True)
    approach_journal = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    submission_code = Column(Text, nullable=True)
    correctness_score = Column(Float, nullable=True)
    complexity_score = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    robustness_score = Column(Float, nullable=True)
    comprehension_answers = Column(Text, nullable=True)
    comprehension_score = Column(Float, nullable=True)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    code = Column(Text, nullable=False)
    diff_lines = Column(Integer, default=0)
    triggered_by = Column(String, nullable=False)


class KeystrokeWindow(Base):
    __tablename__ = "keystroke_windows"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    similarity_score = Column(Float, nullable=False)
    window_data = Column(Text, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
