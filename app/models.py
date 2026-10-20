"""Database tables.

User ──< Exercise
User ──< Block ──< BlockTarget >── Exercise   (the plan)
User ──< SetLog >── Exercise                   (what actually happened)
User ──< RecoverySession                       (deload week: cardio / stretching)
User ──< ExerciseProgress >── Exercise         (state for the progression rules)
"""
from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    # "big" (squat, deadlift: +5kg) or "small" (OHP etc: +2.5kg)
    size = db.Column(db.String(10), nullable=False, default="small")

    __table_args__ = (db.UniqueConstraint("user_id", "name"),)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "size": self.size}


class Block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    length_weeks = db.Column(db.Integer, nullable=False, default=6)
    # "active" -> "completed"
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    targets = db.relationship("BlockTarget", backref="block", cascade="all, delete-orphan")

    def current_week(self, today=None):
        today = today or date.today()
        week = (today - self.start_date).days // 7 + 1
        return max(1, week)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date.isoformat(),
            "length_weeks": self.length_weeks,
            "status": self.status,
            "current_week": self.current_week(),
            "targets": [t.to_dict() for t in self.targets],
        }


class BlockTarget(db.Model):
    """Planned work for one exercise in one week of a block."""

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=False, index=True)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    week = db.Column(db.Integer, nullable=False)
    sets = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)

    __table_args__ = (db.UniqueConstraint("block_id", "exercise_id", "week"),)

    def to_dict(self):
        return {
            "exercise_id": self.exercise_id,
            "week": self.week,
            "sets": self.sets,
            "reps": self.reps,
            "weight_kg": self.weight_kg,
        }


class SetLog(db.Model):
    """One set you actually did."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=True)
    week = db.Column(db.Integer, nullable=True)
    weight_kg = db.Column(db.Float, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    rpe = db.Column(db.Float, nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    performed_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    # Generated on the phone, so a set queued offline and re-sent is only saved once.
    client_id = db.Column(db.String(64), unique=True, nullable=True)

    __table_args__ = (
        # The "what did I do last time?" query hits this index.
        db.Index("ix_setlog_user_exercise_time", "user_id", "exercise_id", "performed_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "exercise_id": self.exercise_id,
            "block_id": self.block_id,
            "week": self.week,
            "weight_kg": self.weight_kg,
            "reps": self.reps,
            "rpe": self.rpe,
            "notes": self.notes,
            "performed_at": self.performed_at.isoformat(),
        }


class RecoverySession(db.Model):
    """Deload-week activity: cardio or stretching."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    block_id = db.Column(db.Integer, db.ForeignKey("block.id"), nullable=True)
    kind = db.Column(db.String(20), nullable=False)  # "cardio" | "stretch"
    duration_min = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    performed_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "duration_min": self.duration_min,
            "notes": self.notes,
            "performed_at": self.performed_at.isoformat(),
        }


class ExerciseProgress(db.Model):
    """Per-exercise state the progression rules need between blocks."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    consecutive_misses = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("user_id", "exercise_id"),)
