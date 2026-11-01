"""Login, tokens and role-based access."""

from __future__ import annotations

import jwt
import pytest

from app.core import security
from tests.conftest import TEST_PASSWORD, TEST_USERS, login

NEW_PRODUCT = {"sku": "NEW_1", "name": "New", "category_code": "FOODS", "unit_price": "1.00"}


# ---------- password hashing and tokens ----------

def test_password_hash_round_trip_and_salting():
    first, second = security.hash_password("correct horse"), security.hash_password("correct horse")
    assert first != second                                   # random salt each time
    assert first.startswith("pbkdf2_sha256$600000$")
    assert "correct horse" not in first
    assert security.verify_password("correct horse", first)
    assert not security.verify_password("wrong horse", first)
    assert not security.verify_password("anything", "not-a-valid-hash")


def test_token_round_trip_and_expiry():
    token, lifetime = security.create_access_token(7, "manager", expires_minutes=5)
    assert lifetime == 300
    claims = security.decode_access_token(token)
    assert claims["sub"] == "7" and claims["role"] == "manager"
    expired, _ = security.create_access_token(7, "manager", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(expired)


# ---------- login ----------

def test_login_returns_token_and_user(api):
    response = api.post("/api/v1/auth/login", data={"username": "MANAGER@test.local", "password": TEST_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "manager"
    assert "hashed_password" not in body["user"]


@pytest.mark.parametrize("email, password", [
    ("manager@test.local", "wrong-password-1"),     # wrong password
    ("nobody@test.local", TEST_PASSWORD),           # unknown email
    ("inactive@test.local", TEST_PASSWORD),         # deactivated account
])
def test_login_failures_all_look_the_same(api, email, password):
    response = api.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}


def test_me(api):
    assert api.get("/api/v1/auth/me", headers=login(api, "viewer")).json()["email"] == "viewer@test.local"


# ---------- protection ----------

def test_health_is_public_but_data_needs_login(api):
    assert api.get("/api/v1/health").status_code == 200
    for path in ["/api/v1/products", "/api/v1/products/1", "/api/v1/categories", "/api/v1/auth/me"]:
        response = api.get(path)
        assert response.status_code == 401, path
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("token", [
    "not-a-jwt",
    jwt.encode({"sub": "1", "exp": 9999999999}, "a-different-secret", algorithm="HS256"),   # forged
])
def test_bad_tokens_rejected(api, token):
    assert api.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_token_rejected(api):
    token, _ = security.create_access_token(1, "admin", expires_minutes=-1)
    response = api.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401 and "expired" in response.json()["detail"]


def test_deactivated_user_loses_access_immediately(api):
    viewer_headers = login(api, "viewer")
    admin = login(api, "admin")
    viewer_id = api.get("/api/v1/auth/me", headers=viewer_headers).json()["id"]
    api.patch(f"/api/v1/users/{viewer_id}", json={"is_active": False}, headers=admin)
    assert api.get("/api/v1/products", headers=viewer_headers).status_code == 401   # token still valid, user not


@pytest.mark.parametrize("role, can_read, can_write, can_manage_users", [
    ("viewer", 200, 403, 403),
    ("manager", 200, 201, 403),
    ("admin", 200, 201, 200),
])
def test_role_permissions(api, role, can_read, can_write, can_manage_users):
    headers = login(api, role)
    assert api.get("/api/v1/products", headers=headers).status_code == can_read
    assert api.post("/api/v1/products", json=NEW_PRODUCT, headers=headers).status_code == can_write
    assert api.patch("/api/v1/products/1", json={"name": "x"}, headers=headers).status_code in (
        (403,) if can_write == 403 else (200,))
    assert api.get("/api/v1/users", headers=headers).status_code == can_manage_users


# ---------- user management (admin) ----------

def test_admin_creates_user_who_can_log_in(api):
    admin = login(api, "admin")
    response = api.post("/api/v1/users", headers=admin, json={
        "email": " New.Person@Test.local ", "full_name": "New Person", "password": "a-long-password", "role": "viewer"})
    assert response.status_code == 201 and response.json()["email"] == "new.person@test.local"
    assert api.post("/api/v1/auth/login",
                    data={"username": "new.person@test.local", "password": "a-long-password"}).status_code == 200


@pytest.mark.parametrize("change", [{"password": "short"}, {"email": "not-an-email"}, {"role": "superuser"}])
def test_invalid_new_user_rejected(api, change):
    payload = {"email": "x@test.local", "full_name": "X", "password": "a-long-password", **change}
    assert api.post("/api/v1/users", json=payload, headers=login(api, "admin")).status_code == 422


def test_duplicate_email_is_409(api):
    payload = {"email": TEST_USERS["viewer"][0], "full_name": "Dup", "password": "a-long-password"}
    assert api.post("/api/v1/users", json=payload, headers=login(api, "admin")).status_code == 409


def test_last_admin_cannot_be_demoted_or_self_deactivated(api):
    admin = login(api, "admin")
    admin_id = api.get("/api/v1/auth/me", headers=admin).json()["id"]
    response = api.patch(f"/api/v1/users/{admin_id}", json={"role": "viewer"}, headers=admin)
    assert response.status_code == 400 and "last active admin" in response.json()["detail"]
    assert api.patch(f"/api/v1/users/{admin_id}", json={"is_active": False}, headers=admin).status_code == 400


def test_admin_resets_password(api):
    admin = login(api, "admin")
    viewer_id = api.get("/api/v1/auth/me", headers=login(api, "viewer")).json()["id"]
    assert api.patch(f"/api/v1/users/{viewer_id}", json={"password": "brand-new-password"},
                     headers=admin).status_code == 200
    assert api.post("/api/v1/auth/login", data={"username": "viewer@test.local",
                                                "password": TEST_PASSWORD}).status_code == 401
    assert api.post("/api/v1/auth/login", data={"username": "viewer@test.local",
                                                "password": "brand-new-password"}).status_code == 200
