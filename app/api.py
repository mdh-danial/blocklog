"""JSON API used by the frontend. Every route needs a logged-in user,
and every query is filtered by current_user so people only see their own data."""
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from . import db
from .models import Block, BlockTarget, Exercise, ExerciseProgress, RecoverySession, SetLog
from .progression import next_miss_count, progression, target_was_hit

bp = Blueprint("api", __name__)

# Sets within this window of your most recent set count as "last session".
SESSION_WINDOW = timedelta(hours=6)


# --- helpers -----------------------------------------------------------------

def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="expected a JSON object")
    return data


def _bad(message):
    return jsonify(error=message), 400


def _own_exercise(exercise_id):
    ex = db.session.get(Exercise, exercise_id)
    if ex is None or ex.user_id != current_user.id:
        abort(404)
    return ex


def _own_block(block_id):
    block = db.session.get(Block, block_id)
    if block is None or block.user_id != current_user.id:
        abort(404)
    return block


def _active_block():
    return (
        Block.query.filter_by(user_id=current_user.id, status="active")
        .order_by(Block.start_date.desc())
        .first()
    )


@bp.errorhandler(400)
@bp.errorhandler(404)
def _error(err):
    return jsonify(error=getattr(err, "description", str(err))), err.code


# --- exercises ---------------------------------------------------------------

@bp.get("/exercises")
@login_required
def list_exercises():
    rows = Exercise.query.filter_by(user_id=current_user.id).order_by(Exercise.name).all()
    return jsonify([e.to_dict() for e in rows])


@bp.post("/exercises")
@login_required
def create_exercise():
    data = _json()
    name = str(data.get("name", "")).strip()
    size = data.get("size", "small")
    if not name:
        return _bad("name is required")
    if size not in ("big", "small"):
        return _bad("size must be 'big' or 'small'")
    if Exercise.query.filter_by(user_id=current_user.id, name=name).first():
        return _bad("you already have an exercise with that name")
    ex = Exercise(user_id=current_user.id, name=name, size=size)
    db.session.add(ex)
    db.session.commit()
    return jsonify(ex.to_dict()), 201


@bp.get("/exercises/<int:exercise_id>/summary")
@login_required
def exercise_summary(exercise_id):
    """The core feature: what did I do last time, what's my best, what's today's target."""
    ex = _own_exercise(exercise_id)
    base = SetLog.query.filter_by(user_id=current_user.id, exercise_id=ex.id)

    latest = base.order_by(SetLog.performed_at.desc()).first()
    last_session = []
    if latest:
        window_start = latest.performed_at - SESSION_WINDOW
        last_session = (
            base.filter(SetLog.performed_at >= window_start)
            .order_by(SetLog.performed_at)
            .all()
        )

    best = base.order_by(SetLog.weight_kg.desc(), SetLog.reps.desc()).first()

    target = None
    block = _active_block()
    if block:
        t = BlockTarget.query.filter_by(
            block_id=block.id, exercise_id=ex.id, week=block.current_week()
        ).first()
        target = t.to_dict() if t else None

    return jsonify(
        exercise=ex.to_dict(),
        last_session=[s.to_dict() for s in last_session],
        best=best.to_dict() if best else None,
        target=target,
    )


# --- set logging ---------------------------------------------------------------

@bp.post("/sets")
@login_required
def log_set():
    data = _json()

    # Offline queue may resend the same set: client_id makes the request idempotent.
    client_id = data.get("client_id")
    if client_id:
        existing = SetLog.query.filter_by(client_id=client_id).first()
        if existing:
            if existing.user_id != current_user.id:
                return _bad("client_id already used")
            return jsonify(existing.to_dict()), 200

    try:
        exercise_id = int(data["exercise_id"])
        weight = float(data["weight_kg"])
        reps = int(data["reps"])
        rpe = float(data["rpe"]) if data.get("rpe") not in (None, "") else None
    except (KeyError, TypeError, ValueError):
        return _bad("exercise_id, weight_kg and reps are required numbers")

    if weight < 0 or reps < 1:
        return _bad("weight must be >= 0 and reps >= 1")
    if rpe is not None and not 1 <= rpe <= 10:
        return _bad("rpe must be between 1 and 10")

    _own_exercise(exercise_id)

    performed_at = None
    if data.get("performed_at"):
        try:
            performed_at = datetime.fromisoformat(data["performed_at"])
        except ValueError:
            return _bad("performed_at must be an ISO datetime")

    block = _active_block()
    s = SetLog(
        user_id=current_user.id,
        exercise_id=exercise_id,
        block_id=block.id if block else None,
        week=block.current_week() if block else None,
        weight_kg=weight,
        reps=reps,
        rpe=rpe,
        notes=(data.get("notes") or None),
        client_id=client_id,
    )
    if performed_at:
        s.performed_at = performed_at
    db.session.add(s)
    db.session.commit()
    return jsonify(s.to_dict()), 201


@bp.get("/sets")
@login_required
def list_sets():
    q = SetLog.query.filter_by(user_id=current_user.id)
    if request.args.get("exercise_id"):
        q = q.filter_by(exercise_id=int(request.args["exercise_id"]))
    limit = min(int(request.args.get("limit", 50)), 200)
    rows = q.order_by(SetLog.performed_at.desc()).limit(limit).all()
    return jsonify([s.to_dict() for s in rows])


@bp.delete("/sets/<int:set_id>")
@login_required
def delete_set(set_id):
    s = db.session.get(SetLog, set_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    db.session.delete(s)
    db.session.commit()
    return "", 204


# --- blocks --------------------------------------------------------------------

@bp.post("/blocks")
@login_required
def create_block():
    """Body: {name, start_date?, length_weeks?, targets: [{exercise_id, week, sets, reps, weight_kg}]}"""
    data = _json()
    name = str(data.get("name", "")).strip()
    if not name:
        return _bad("name is required")
    try:
        start = date.fromisoformat(data["start_date"]) if data.get("start_date") else date.today()
        length = int(data.get("length_weeks", 6))
    except ValueError:
        return _bad("start_date must be YYYY-MM-DD and length_weeks a number")

    if _active_block():
        return _bad("finish your active block before starting a new one")

    block = Block(user_id=current_user.id, name=name, start_date=start, length_weeks=length)
    for t in data.get("targets", []):
        _own_exercise(int(t["exercise_id"]))
        week = int(t["week"])
        if not 1 <= week <= length:
            return _bad(f"target week {week} is outside the block")
        block.targets.append(
            BlockTarget(
                exercise_id=int(t["exercise_id"]),
                week=week,
                sets=int(t["sets"]),
                reps=int(t["reps"]),
                weight_kg=float(t["weight_kg"]),
            )
        )
    db.session.add(block)
    db.session.commit()
    return jsonify(block.to_dict()), 201


@bp.get("/blocks/active")
@login_required
def active_block():
    block = _active_block()
    return jsonify(block.to_dict() if block else None)


def _block_recommendations(block):
    """Run the progression rules for every exercise planned in the block's final week."""
    results = []
    final_targets = [t for t in block.targets if t.week == block.length_weeks]
    for t in final_targets:
        ex = db.session.get(Exercise, t.exercise_id)
        logs = SetLog.query.filter_by(
            user_id=current_user.id, block_id=block.id, exercise_id=ex.id, week=t.week
        ).all()
        hit = target_was_hit(t.sets, t.reps, t.weight_kg, [(s.weight_kg, s.reps) for s in logs])
        rpes = [s.rpe for s in logs if s.rpe is not None]
        hardest_rpe = max(rpes) if rpes else None

        progress = ExerciseProgress.query.filter_by(
            user_id=current_user.id, exercise_id=ex.id
        ).first()
        misses = progress.consecutive_misses if progress else 0

        rec = progression(ex.size, t.weight_kg, hit, hardest_rpe, misses)
        results.append((ex, progress, misses, rec))
    return results


@bp.get("/blocks/<int:block_id>/recommendations")
@login_required
def preview_recommendations(block_id):
    """Preview only. Nothing is saved."""
    block = _own_block(block_id)
    return jsonify(
        [{"exercise": ex.to_dict(), **rec.to_dict()} for ex, _, _, rec in _block_recommendations(block)]
    )


@bp.post("/blocks/<int:block_id>/complete")
@login_required
def complete_block(block_id):
    """Finish the block: save miss counters and return the suggestions."""
    block = _own_block(block_id)
    if block.status != "active":
        return _bad("block is already completed")

    out = []
    for ex, progress, misses, rec in _block_recommendations(block):
        if progress is None:
            progress = ExerciseProgress(user_id=current_user.id, exercise_id=ex.id)
            db.session.add(progress)
        progress.consecutive_misses = next_miss_count(rec, misses)
        out.append({"exercise": ex.to_dict(), **rec.to_dict()})

    block.status = "completed"
    db.session.commit()
    return jsonify(out)


# --- recovery week ----------------------------------------------------------------

@bp.post("/recovery")
@login_required
def log_recovery():
    data = _json()
    kind = data.get("kind")
    if kind not in ("cardio", "stretch"):
        return _bad("kind must be 'cardio' or 'stretch'")
    try:
        minutes = int(data["duration_min"])
    except (KeyError, TypeError, ValueError):
        return _bad("duration_min is required")
    if minutes < 1:
        return _bad("duration_min must be at least 1")
    r = RecoverySession(
        user_id=current_user.id, kind=kind, duration_min=minutes, notes=data.get("notes") or None
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201


@bp.get("/recovery")
@login_required
def list_recovery():
    rows = (
        RecoverySession.query.filter_by(user_id=current_user.id)
        .order_by(RecoverySession.performed_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([r.to_dict() for r in rows])
