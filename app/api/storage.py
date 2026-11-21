"""Chat history and feedback (SQLAlchemy 2; SQLite for development and tests, PostgreSQL in Docker).

Tables:
- chat_session: one conversation;
- turn: one question about one image, with the answer, proof, citations, sign boxes,
  stage summary, cost and time;
- feedback: thumbs up/down and an optional corrected answer for a turn.

Feedback is stored for the dashboard and the thesis only. The pipeline never reads it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "chat_session"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    turns: Mapped[list["Turn"]] = relationship(back_populates="session", order_by="Turn.created_at")


class Turn(Base):
    __tablename__ = "turn"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_session.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    question: Mapped[str] = mapped_column(Text)
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")    # running | done | error
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    basis: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    proof: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    signs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    stages: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    session: Mapped[ChatSession] = relationship(back_populates="turns")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="turn", order_by="Feedback.created_at")


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    turn_id: Mapped[str] = mapped_column(ForeignKey("turn.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    thumb: Mapped[str | None] = mapped_column(String(4), nullable=True)            # up | down
    corrected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn: Mapped[Turn] = relationship(back_populates="feedback")


class Store:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///"):
            from pathlib import Path
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(url, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def db(self) -> Session:
        return self._sessions()

    def ping(self) -> bool:
        try:
            with self.db() as s:
                s.execute(select(1))
            return True
        except Exception:
            return False

    def new_session(self) -> ChatSession:
        with self.db() as s:
            cs = ChatSession()
            s.add(cs)
            s.commit()
            return cs

    def get_session(self, session_id: str) -> ChatSession | None:
        with self.db() as s:
            return s.get(ChatSession, session_id)

    def start_turn(self, session_id: str, question: str, image_sha256: str) -> Turn:
        with self.db() as s:
            t = Turn(session_id=session_id, question=question, image_sha256=image_sha256)
            s.add(t)
            s.commit()
            return t

    def finish_turn(self, turn_id: str, **fields: Any) -> Turn:
        with self.db() as s:
            t = s.get(Turn, turn_id)
            for k, v in fields.items():
                setattr(t, k, v)
            s.commit()
            _ = list(t.feedback)
            return t

    def get_turn(self, turn_id: str) -> Turn | None:
        with self.db() as s:
            t = s.get(Turn, turn_id)
            if t is not None:
                _ = list(t.feedback)
            return t

    def turns(self, session_id: str) -> list[Turn]:
        with self.db() as s:
            rows = s.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.created_at)).all()
            for t in rows:
                _ = list(t.feedback)
            return list(rows)

    def add_feedback(self, turn_id: str, thumb: str | None, corrected_answer: str | None,
                     note: str | None) -> Feedback:
        with self.db() as s:
            f = Feedback(turn_id=turn_id, thumb=thumb, corrected_answer=corrected_answer, note=note)
            s.add(f)
            s.commit()
            return f
