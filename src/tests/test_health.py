from http import HTTPStatus

from fastapi.testclient import TestClient

from src.api.api import app

CLIENT = TestClient(app)


def test_health_home():
    response = CLIENT.get("/health/")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"message": "Hello from Fast app!"}
