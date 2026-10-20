from datetime import date, timedelta

from tests.conftest import register


def test_api_requires_login(client):
    assert client.get("/api/exercises").status_code == 401


def test_index_redirects_to_login(client):
    res = client.get("/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_register_login_logout(client):
    register(client)
    assert client.get("/api/exercises").status_code == 200
    client.post("/logout")
    assert client.get("/api/exercises").status_code == 401
    client.post("/login", data={"email": "danial@example.com", "password": "password123"})
    assert client.get("/api/exercises").status_code == 200


def test_wrong_password_rejected(client):
    register(client)
    client.post("/logout")
    client.post("/login", data={"email": "danial@example.com", "password": "nope-nope"})
    assert client.get("/api/exercises").status_code == 401


def test_short_password_rejected(client):
    register(client, password="short")
    assert client.get("/api/exercises").status_code == 401


def test_log_set_and_recall(user_client, squat):
    for reps in (5, 5, 4):
        res = user_client.post(
            "/api/sets", json={"exercise_id": squat["id"], "weight_kg": 100, "reps": reps, "rpe": 8}
        )
        assert res.status_code == 201

    summary = user_client.get(f"/api/exercises/{squat['id']}/summary").get_json()
    assert [s["reps"] for s in summary["last_session"]] == [5, 5, 4]
    assert summary["best"]["weight_kg"] == 100


def test_validation(user_client, squat):
    bad = [
        {"exercise_id": squat["id"], "weight_kg": 100},                         # no reps
        {"exercise_id": squat["id"], "weight_kg": -5, "reps": 5},               # negative weight
        {"exercise_id": squat["id"], "weight_kg": 100, "reps": 5, "rpe": 11},   # rpe > 10
    ]
    for body in bad:
        assert user_client.post("/api/sets", json=body).status_code == 400


def test_offline_resend_is_not_duplicated(user_client, squat):
    body = {"exercise_id": squat["id"], "weight_kg": 80, "reps": 8, "client_id": "abc-123"}
    assert user_client.post("/api/sets", json=body).status_code == 201
    assert user_client.post("/api/sets", json=body).status_code == 200  # same set again
    assert len(user_client.get("/api/sets").get_json()) == 1


def test_users_cannot_see_each_others_data(client, app):
    register(client, email="a@example.com")
    ex = client.post("/api/exercises", json={"name": "Deadlift", "size": "big"}).get_json()
    client.post("/logout")

    register(client, email="b@example.com")
    assert client.get("/api/exercises").get_json() == []
    assert client.get(f"/api/exercises/{ex['id']}/summary").status_code == 404


def test_block_completion_gives_recommendation(user_client, squat):
    # A 6-week block that started 5 weeks ago, so "today" is week 6 (the final week).
    start = (date.today() - timedelta(weeks=5)).isoformat()
    block = user_client.post(
        "/api/blocks",
        json={
            "name": "Block 1",
            "start_date": start,
            "length_weeks": 6,
            "targets": [{"exercise_id": squat["id"], "week": 6, "sets": 3, "reps": 3, "weight_kg": 120}],
        },
    ).get_json()
    assert block["current_week"] == 6

    for _ in range(3):
        user_client.post("/api/sets", json={"exercise_id": squat["id"], "weight_kg": 120, "reps": 3, "rpe": 9})

    preview = user_client.get(f"/api/blocks/{block['id']}/recommendations").get_json()
    assert preview[0]["action"] == "increase"
    assert preview[0]["new_weight"] == 125

    done = user_client.post(f"/api/blocks/{block['id']}/complete").get_json()
    assert done[0]["new_weight"] == 125
    assert user_client.get("/api/blocks/active").get_json() is None


def test_missed_block_twice_drops_weight(user_client, squat):
    def run_block(name):
        start = (date.today() - timedelta(weeks=5)).isoformat()
        b = user_client.post(
            "/api/blocks",
            json={
                "name": name,
                "start_date": start,
                "targets": [{"exercise_id": squat["id"], "week": 6, "sets": 3, "reps": 3, "weight_kg": 120}],
            },
        ).get_json()
        # Only 2 of 3 target sets done -> miss
        for _ in range(2):
            user_client.post("/api/sets", json={"exercise_id": squat["id"], "weight_kg": 120, "reps": 3, "rpe": 10})
        return user_client.post(f"/api/blocks/{b['id']}/complete").get_json()[0]

    assert run_block("Block 1")["action"] == "repeat"
    assert run_block("Block 2")["action"] == "drop"


def test_recovery_logging(user_client):
    res = user_client.post("/api/recovery", json={"kind": "stretch", "duration_min": 20})
    assert res.status_code == 201
    assert user_client.post("/api/recovery", json={"kind": "yoga", "duration_min": 20}).status_code == 400


def test_pwa_files_served(client):
    assert client.get("/sw.js").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/healthz").get_json() == {"status": "ok"}
