from fastapi.testclient import TestClient

from app.main import app, SECRET_API_KEY


client = TestClient(app)


def test_batch_classify_requires_api_key():
    images = [
        [[0 for _ in range(28)] for _ in range(28)]
        for _ in range(2)
    ]

    response = client.post("/classify/batch", json={"images": images})

    assert response.status_code == 401


def test_batch_classify_returns_result_for_each_image():
    images = [
        [[0 for _ in range(28)] for _ in range(28)]
        for _ in range(3)
    ]

    response = client.post(
        "/classify/batch",
        json={"images": images},
        headers={"X-API-Key": SECRET_API_KEY},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["count"] == 3
    assert len(data["results"]) == 3

    for result in data["results"]:
        assert "prediction" in result
        assert "confidence" in result
        assert "scores" in result


def test_batch_classify_rejects_empty_batch():
    response = client.post(
        "/classify/batch",
        json={"images": []},
        headers={"X-API-Key": SECRET_API_KEY},
    )

    assert response.status_code == 400
