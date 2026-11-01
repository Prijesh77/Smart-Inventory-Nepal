# Phase 5, Step 3: Authentication and Role-Based Access

## 1. How it works (plain language)

1. A user sends email + password to `POST /api/v1/auth/login`.
2. The server checks the password against the stored **hash** (the password itself is never stored).
3. If it matches an **active** account, the server returns a signed **token** (a JWT) valid for 60 minutes.
4. The frontend sends that token with every request: `Authorization: Bearer <token>`.
5. For each request, the server checks the signature and expiry, **reloads the user from the database**, and checks their role.

Reloading the user on every request means a deactivated account or a changed role takes effect **immediately**, even if an old token has not expired.

## 2. Roles and access

| Endpoint group | Public | Viewer | Manager | Admin |
|---|---|---|---|---|
| `GET /health`, `POST /auth/login` | ✅ | ✅ | ✅ | ✅ |
| All `GET` (products, sales, categories, suppliers, `/auth/me`) | ❌ 401 | ✅ | ✅ | ✅ |
| Create / change products (and later: stock, orders, approvals) | ❌ 401 | ❌ 403 | ✅ | ✅ |
| `/users` (list, create, change role, deactivate, reset password) | ❌ 401 | ❌ 403 | ❌ 403 | ✅ |

**401** = not logged in, or the token is bad or expired. **403** = logged in but not allowed.

## 3. Security decisions

| Decision | Reason |
|---|---|
| **PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte random salt** (Python standard library) | OWASP-recommended. Avoids compiled hashing packages that Windows Smart App Control may block. The algorithm and iteration count are stored with each hash, so the cost can be raised later |
| Constant-time comparison (`hmac.compare_digest`) | Prevents timing attacks on the hash comparison |
| **Same error and similar timing** for a wrong password, unknown email or inactive account | Attackers cannot discover which emails have accounts (unknown emails are checked against a dummy hash) |
| JWT signed with HS256 using `JWT_SECRET_KEY` from `.env` | Tokens cannot be forged or altered; the secret never appears in code |
| 60-minute token lifetime (`ACCESS_TOKEN_EXPIRE_MINUTES`) | Limits the damage if a token leaks |
| Minimum password length of 10 | Basic strength rule |
| Cannot demote or deactivate the **last active admin**, or deactivate yourself | Prevents locking everyone out |
| `hashed_password` never appears in any API response | Response models only list safe fields |
| SKU, emails and roles validated by Pydantic | Invalid input → 422 before reaching the database |

**Known limits (state in the report):** no login rate limiting or lockout, no refresh tokens, and no HTTPS in local development. A production deployment would add HTTPS (Phase 8) and rate limiting.

## 4. Setup (once)

**a. Add a token secret to `.env`.** Generate one:

```bash
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Add the output to `.env` as `JWT_SECRET_KEY=<the value>`. Without it, a temporary key is used and everyone is logged out whenever the server restarts.

**b. Create the first admin.** The password is typed at a hidden prompt:

```bash
.\.venv\Scripts\python.exe backend\scripts\create_user.py --email you@example.com --name "Your Name" --role admin
```

**c. Log in on `/docs`.** Open http://127.0.0.1:8000/docs, click **Authorize**, and enter your email as *username* plus your password. Every request from the docs page then carries your token. More users (managers, viewers) can be created at `POST /api/v1/users`.

## 5. Tests

`backend/tests/test_auth.py` (22 tests): hashing and salting; token round trip and expiry; login success and three identical-looking failures; public vs protected endpoints; garbage, forged and expired tokens; immediate loss of access after deactivation; the full viewer/manager/admin permission matrix; user creation with email normalisation; invalid input; duplicate email (409); last-admin protection; password reset. The product tests now run as a logged-in manager. **Full suite: 139 passed.**

Checked on the live server: `/health` → 200; `/products` and `/users` without a token → 401; bad login → 401 "Incorrect email or password".
