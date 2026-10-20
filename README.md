# BlockLog

A mobile-first training-block logger. Log a set in a few taps, see exactly what you did last time, and get a suggestion for your next 6-week block based on how the final week went.

I built it because I kept forgetting my weights, reps and sets, and had to dig through notes, photos and old AI chats to find them.

<!-- TODO: add a screenshot or GIF of logging a set on your phone -->
<!-- TODO: add the live link once deployed -->

## Features

- **Fast logging:** weight, reps and RPE with big +/− buttons, prefilled from your last set.
- **Instant recall:** last session, personal best and this week's block target for each exercise.
- **Training blocks:** plan targets per exercise per week (default 6 weeks), and the app tracks which week you're in.
- **Progression suggestions:** per exercise, at the end of a block:

  | Final week result | Suggestion |
  |---|---|
  | Target hit, RPE < 10 | Increase: +5kg big lifts, +2.5kg small lifts |
  | Target hit, RPE 10 | Repeat the block (option: +2.5kg) |
  | Target missed (1st time) | Repeat the block |
  | Target missed again | Drop the weight |

- **Recovery week:** log cardio and stretching sessions.
- **Works offline:** installable PWA. Sets logged with no signal are queued on the phone and synced later, with no duplicates.
- **Multi-user:** accounts with hashed passwords, and every query is scoped to the logged-in user.

## Tech stack

Python · Flask · SQLAlchemy · Flask-Login · PostgreSQL (SQLite locally) · vanilla JavaScript · Service Worker · pytest · GitHub Actions · Render + Neon

## Architecture

```
Phone (PWA)
  index.html + app.js ── fetch JSON ──► Flask app (wsgi.py → app/)
  sw.js caches app shell               ├── auth.py         register / login / logout
  localStorage offline set queue       ├── api.py          /api/... JSON routes
                                       ├── progression.py  pure rules (no DB, no Flask)
                                       └── models.py       SQLAlchemy tables
                                                │
                                                ▼
                                   PostgreSQL (Neon) / SQLite (local)
```

**Data model**

| Table | What it stores |
|---|---|
| `user` | email, hashed password |
| `exercise` | name, size (`big` / `small`, which sets the increment) |
| `block` | name, start date, length (weeks), status |
| `block_target` | planned sets × reps @ weight, per exercise per week |
| `set_log` | each set done: weight, reps, RPE, time, `client_id` for offline dedupe |
| `recovery_session` | cardio / stretching minutes |
| `exercise_progress` | consecutive-miss counter used by the progression rules |

Design decisions worth knowing:
- `progression.py` is a set of pure functions, so the rules are tested as an input → output table without a database.
- The offline queue sends a `client_id` (UUID) with each set. The server treats a repeat of the same id as already saved, so retries are safe.
- `set_log` has a composite index on `(user_id, exercise_id, performed_at)` for the "last time" query.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app wsgi run --debug
```

Open http://127.0.0.1:5000, create an account, add an exercise, log a set.

Run the tests:

```bash
pytest
```

## API

All routes need a logged-in session and return JSON.

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/exercises` | list / create (`{name, size}`) |
| GET | `/api/exercises/<id>/summary` | last session, best, this week's target |
| POST | `/api/sets` | log a set (`{exercise_id, weight_kg, reps, rpe?, client_id?}`) |
| GET | `/api/sets?exercise_id=&limit=` | history |
| DELETE | `/api/sets/<id>` | delete a set |
| POST | `/api/blocks` | start a block with targets |
| GET | `/api/blocks/active` | current block and week |
| GET | `/api/blocks/<id>/recommendations` | preview next-block suggestions |
| POST | `/api/blocks/<id>/complete` | finish the block, save miss counters |
| GET / POST | `/api/recovery` | recovery sessions |

Example: start a block

```json
POST /api/blocks
{
  "name": "Block 1",
  "start_date": "2026-11-02",
  "length_weeks": 6,
  "targets": [
    {"exercise_id": 1, "week": 1, "sets": 3, "reps": 10, "weight_kg": 80},
    {"exercise_id": 1, "week": 6, "sets": 3, "reps": 3,  "weight_kg": 110}
  ]
}
```

## Deploy (free tier)

1. Create a free Postgres database on [Neon](https://neon.com) and copy its connection string.
2. Push this repo to GitHub.
3. On [Render](https://render.com): New → Blueprint → pick the repo (it reads `render.yaml`).
4. In the Render dashboard set `DATABASE_URL` to the Neon string. `SECRET_KEY` is generated for you.
5. Open the URL on your phone in Safari → Share → Add to Home Screen.

The free Render plan sleeps after 15 minutes idle, so the first load can take about a minute.

## Roadmap

- [ ] UI to create a block and its weekly targets (currently API only)
- [ ] End-of-block screen showing suggestions, accept / pick alternative
- [ ] Missed-week handling in the UI (`plan_after_gap` exists in `progression.py`)
- [ ] Progress charts: weekly volume, estimated 1RM trend, block vs block
- [ ] Calisthenics skill progressions
- [ ] Import old notes (paste text, parse into sets)
- [ ] CSRF protection on forms (Flask-WTF) and rate-limited login
- [ ] Database migrations (Flask-Migrate) instead of `create_all()`
- [ ] Load test with Locust and record the numbers

## Disclaimer

BlockLog suggests weights from simple rules you configure. It's a logging tool, not coaching or medical advice.
