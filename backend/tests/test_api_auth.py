from pathlib import Path

from tests.conftest import App, start_app


def test_signup_signs_in_with_an_httponly_cookie(app: App) -> None:
    user = app.signup("Ana@Example.com ")
    assert user["email"] == "ana@example.com"
    cookie = app.client.cookies.jar
    [session] = [c for c in cookie if c.name == "pdfa_session"]
    assert session.has_nonstandard_attr("HttpOnly") and session.path == "/api"
    assert app.client.get("/api/auth/user").json() == user


def test_signin_signout_and_wrong_password(app: App) -> None:
    user = app.signup()
    assert app.client.post("/api/auth/signout").status_code == 204
    assert app.client.get("/api/auth/user").json() is None
    assert app.client.get("/api/pdfs").status_code == 401

    wrong = app.client.post("/api/auth/signin", json={"email": "ana@example.com", "password": "pogresna123"})
    assert wrong.status_code == 401 and wrong.json()["detail"] == "Pogrešna adresa ili lozinka."
    unknown = app.client.post("/api/auth/signin", json={"email": "niko@example.com", "password": "lozinka123"})
    assert unknown.status_code == 401 and unknown.json() == wrong.json()

    ok = app.client.post("/api/auth/signin", json={"email": "ANA@example.com", "password": "lozinka123"})
    assert ok.status_code == 200 and ok.json() == user


def test_signup_rejects_duplicates_and_bad_passwords(app: App) -> None:
    app.signup()
    again = app.client.post("/api/auth/signup", json={"email": "ana@example.com", "password": "lozinka123"})
    assert again.status_code == 409
    short = app.client.post("/api/auth/signup", json={"email": "b@example.com", "password": "kratka"})
    assert short.status_code == 422
    # 40 two-byte letters: 40 characters but 80 bytes, past what bcrypt reads.
    long = app.client.post("/api/auth/signup", json={"email": "c@example.com", "password": "č" * 40})
    assert long.status_code == 422 and long.json()["detail"][0]["msg"].startswith("Lozinka može imati najviše 72 bajta")


def test_a_forged_or_foreign_cookie_is_ignored(app: App) -> None:
    app.client.cookies.set("pdfa_session", "not-a-token", path="/api")
    assert app.client.get("/api/auth/user").json() is None
    assert app.client.get("/api/pdfs").status_code == 401


def test_signup_can_be_closed(tmp_path: Path) -> None:
    client, _ = start_app(tmp_path, allow_signup=False)
    with client:
        response = client.post("/api/auth/signup", json={"email": "a@example.com", "password": "lozinka123"})
        assert response.status_code == 403
