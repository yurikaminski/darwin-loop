import os

os.environ.update(INGEST_TOKEN="t", DASH_USER="u", DASH_PASS="p")
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

c = TestClient(main.app, base_url="https://testserver")


def test_login_flow():
    assert c.get("/", follow_redirects=False).headers["location"] == "/login"
    assert c.get("/api/overview").status_code == 401
    assert c.post("/login", data={"user": "u", "password": "x"}, follow_redirects=False).headers["location"] == "/login?error=1"
    r = c.post("/login", data={"user": "u", "password": "p"}, follow_redirects=False)
    assert r.headers["location"] == "/" and "dl_session" in c.cookies
    assert c.get("/").status_code == 200


def test_squad_assignment_validation():
    import pytest
    assert main._assignment({"email": " Ana@X.com ", "squad": " Core "}) == ("ana@x.com", "Core")
    assert main._assignment({"email": "a@x.com", "squad": ""}) == ("a@x.com", None)
    for bad in ({"email": "nope"}, {"email": "a@x.com", "squad": "x'; DROP"}, {"email": "a@x.com", "squad": "x" * 41}):
        with pytest.raises(main.HTTPException):
            main._assignment(bad)
    assert TestClient(main.app, base_url="https://testserver").post("/api/people", json={"email": "a@x.com"}).status_code == 401
