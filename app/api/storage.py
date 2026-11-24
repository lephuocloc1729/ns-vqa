"""Chat history and feedback (SQLAlchemy 2; SQLite for development and tests, PostgreSQL in Docker).

Tables:
- chat_session: one conversation;
- turn: one question about one image, with the answer, proof, citations, sign boxes,
  stage summary, cost and time;
- feedback: thumbs up/down and an optional corrected answer for a turn;
- app_setting: live overrides of .env settings, changed on the admin site (app/api/live.py);
- site_account: one login per tester for the site's password prompt (app/api/accounts.py).

Feedback is stored for the dashboard and the thesis only. The pipeline never reads it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text, create_engine, func, inspect, select, text
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
    retrieved: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # RAG laws
    stages: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    account: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # the site login that asked
    understood_as: Mapped[str | None] = mapped_column(Text, nullable=True)   # a follow-up, rewritten (app/api/followup.py)
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


class AppSetting(Base):
    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class SiteAccount(Base):
    __tablename__ = "site_account"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    password_set_at: Mapped[datetime] = mapped_column(default=_now)


class Store:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///"):
            from pathlib import Path
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(url, pool_pre_ping=True)
        self._create_tables()
        self._add_missing_columns()
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def _create_tables(self) -> None:
        """Create missing tables. Several server processes may start at once and race to create
        the same table; the loser sees "already exists" and simply checks again."""
        import time
        from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
        for attempt in range(5):
            try:
                Base.metadata.create_all(self.engine)
                return
            except (OperationalError, ProgrammingError, IntegrityError) as e:
                if "already exists" not in str(e) and "duplicate" not in str(e).lower() or attempt == 4:
                    raise
                time.sleep(0.2 * (attempt + 1))

    def _add_missing_columns(self) -> None:
        """Additive migration: a database made by an older version gets the newer nullable columns."""
        cols = {c["name"] for c in inspect(self.engine).get_columns("turn")}
        with self.engine.begin() as conn:
            for col in Turn.__table__.columns:
                if col.name not in cols:
                    conn.execute(text(f'ALTER TABLE turn ADD COLUMN {col.name} {col.type.compile(self.engine.dialect)}'))

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

    def start_turn(self, session_id: str, question: str, image_sha256: str, account: str | None = None,
                   understood_as: str | None = None) -> Turn:
        with self.db() as s:
            t = Turn(session_id=session_id, question=question, image_sha256=image_sha256, account=account,
                     understood_as=understood_as)
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

    def previous_question(self, session_id: str, image_sha256: str) -> str | None:
        """The last question asked about this photo in this session, as it was answered."""
        with self.db() as s:
            t = s.scalars(select(Turn).where(Turn.session_id == session_id, Turn.image_sha256 == image_sha256)
                          .order_by(Turn.created_at.desc()).limit(1)).first()
            return (t.understood_as or t.question) if t is not None else None

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

    # ------------------------------------------------------------------ live settings
    def settings_overrides(self) -> dict[str, str]:
        with self.db() as s:
            return {r.key: r.value for r in s.scalars(select(AppSetting)).all()}

    def set_overrides(self, values: dict[str, str | None]) -> None:
        """Set each key; None removes the override (back to the .env value)."""
        with self.db() as s:
            for k, v in values.items():
                row = s.get(AppSetting, k)
                if v is None:
                    if row is not None:
                        s.delete(row)
                elif row is None:
                    s.add(AppSetting(key=k, value=v))
                else:
                    row.value = v
            s.commit()

    # ------------------------------------------------------------------ site accounts
    def accounts(self) -> list[SiteAccount]:
        with self.db() as s:
            return list(s.scalars(select(SiteAccount).order_by(SiteAccount.created_at)).all())

    def get_account(self, name: str) -> SiteAccount | None:
        with self.db() as s:
            return s.get(SiteAccount, name)

    def add_account(self, name: str, password_hash: str, note: str | None) -> SiteAccount:
        with self.db() as s:
            a = SiteAccount(name=name, password_hash=password_hash, note=note)
            s.add(a)
            s.commit()
            return a

    def update_account(self, name: str, **fields: Any) -> SiteAccount | None:
        with self.db() as s:
            a = s.get(SiteAccount, name)
            if a is None:
                return None
            for k, v in fields.items():
                setattr(a, k, v)
            s.commit()
            return a

    def account_usage(self) -> dict[str, tuple[int, datetime | None]]:
        """Per account: questions asked and the time of the last one."""
        with self.db() as s:
            rows = s.execute(select(Turn.account, func.count(), func.max(Turn.created_at))
                             .where(Turn.account.is_not(None)).group_by(Turn.account)).all()
            return {r[0]: (int(r[1]), r[2]) for r in rows}

    # ------------------------------------------------------------------ admin reads
    def turns_between(self, since: datetime | None, until: datetime | None) -> list[Turn]:
        with self.db() as s:
            q = select(Turn).order_by(Turn.created_at)
            if since is not None:
                q = q.where(Turn.created_at >= since)
            if until is not None:
                q = q.where(Turn.created_at < until)
            rows = s.scalars(q).all()
            for t in rows:
                _ = list(t.feedback)
            return list(rows)
