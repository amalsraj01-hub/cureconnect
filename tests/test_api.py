"""The web surface: the app serving its own frontend, health, safety, limit.

Everything here is offline and model-free. Red-flag symptoms answer before
the classifier or Overpass is consulted, and the one full-path test patches
app.main.find_doctors, so the suite never opens a network socket.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Heart attack is a red flag, so this short-circuits before model + Overpass.
RED_FLAG = "I think I am having a heart attack"


def _post(symptoms, ip):
    # X-Forwarded-For is what the rate limiter keys on behind a proxy (Render),
    # and it is how each test gets its own bucket: the limiter is module-global,
    # so tests sharing an IP would count each other's requests.
    return client.post("/recommend",
                       json={"symptoms": symptoms, "lat": 11.8745, "lng": 75.3704},
                       headers={"X-Forwarded-For": ip})


def test_health_is_up():
    assert client.get("/health").json() == {"status": "ok"}


def test_the_root_answers_with_the_frontend():
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>CureConnect</title>" in r.text
    # The ODbL credit is a licence condition, and proof the real file was
    # served rather than a directory listing or a stub page.
    assert "OpenStreetMap contributors (ODbL)" in r.text


def test_the_static_mount_does_not_swallow_the_api_docs():
    # The frontend Mount sits at "/" as the last route. The API's own routes
    # must still win: /docs is what you open to try the API by hand.
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_red_flag_symptoms_bypass_model_and_search():
    r = _post(RED_FLAG, "test-api-emergency")
    assert r.status_code == 200
    body = r.json()
    assert body["emergency"] is True
    assert "112" in body["message"]
    assert "disclaimer" in body


def test_a_real_symptom_run_is_ranked_without_touching_the_network(monkeypatch):
    fake_places = [{
        "id": 1,
        "displayName": {"text": "Test Clinic"},
        "location": {"latitude": 11.8746, "longitude": 75.3705},
        "speciality_match": False,
        "kind": "clinic",
        "phone": "",
        "website": "",
        "opening_hours": "",
    }]
    monkeypatch.setattr("app.main.find_doctors",
                        lambda specialist, lat, lng: fake_places)
    r = _post("I have had heartburn and acid reflux every night for a week",
              "test-api-full")
    assert r.status_code == 200
    body = r.json()
    assert body["emergency"] is False
    assert body["doctors"][0]["name"] == "Test Clinic"
    assert body["doctors"][0]["distance_km"] < 1


def test_rate_limit_is_what_a_browser_would_see():
    ip = "test-api-ratelimit"
    for _ in range(10):
        assert _post(RED_FLAG, ip).status_code == 200
    r = _post(RED_FLAG, ip)
    assert r.status_code == 429
    # app/main.py exposes this header to CORS precisely so the page can read
    # it and tell the user how long to wait.
    assert int(r.headers["Retry-After"]) >= 1
