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
