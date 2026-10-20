import pytest

from app import create_app, db
from app.config import TestConfig


@pytest.fixture
def app():
    app = create_app(TestConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, email="danial@example.com", password="password123"):
    return client.post("/register", data={"email": email, "password": password})


@pytest.fixture
def user_client(client):
    """A client that is already logged in."""
    register(client)
    return client


@pytest.fixture
def squat(user_client):
    res = user_client.post("/api/exercises", json={"name": "Back squat", "size": "big"})
    return res.get_json()
