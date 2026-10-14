# Security

What the application does to protect accounts and data, and what remains for a production
deployment. Report a vulnerability privately to the repository owners rather than in a public
issue.

## Implemented

| Area | Measure | Where |
|---|---|---|
| Passwords | Argon2id (19 MiB, 2 iterations, PHC string), minimum 10 characters, list of common passwords refused | `backend/app/security.py`, `schemas/auth.py` |
| Sessions | JWT access token (15 min) kept in memory by the interface; opaque 256-bit refresh token in an HttpOnly, SameSite=Strict cookie scoped to `/api/v1/auth`, stored hashed, rotated on every use; reuse of a rotated token revokes the whole family | `services/auth.py`, `api/v1/auth.py` |
| CSRF | Cookie used only on `/auth/refresh` and `/auth/logout`, which also require the `X-Requested-With: SALVA` header | `api/v1/auth.py` |
| Tenancy | Every query on lots, analyses, storage sites and users is filtered by the caller's organization; other organizations' identifiers answer 404 | services and repositories |
| Roles | `admin` manages storage sites and users; `operator` works on lots | `deps.require_admin` |
| Rate limits | Sign-in/registration 10/min per IP, session refresh 60/min per IP, computations 60/h and explanations 30/h per user, `429` with `Retry-After` | `rate_limit.py`, `deps.py` |
| Input | Strict Pydantic schemas (unknown fields refused), bounded numbers and strings, 64 KiB body limit (`413`), errors as `application/problem+json` without stack traces | `schemas/`, `errors.py`, `main.py` |
| Headers | CSP `default-src 'self'` without inline scripts, `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy`, `no-store` on API responses | `main.py` |
| Language model | Only computed facts are sent (lot notes never are); the output is validated (numbers, forbidden wording, decision, language, markup) and replaced by the template text when rejected; rejections are audited | `llm/`, `services/explanation.py` |
| Secrets | Read from the environment only; production refuses the development JWT secret and a `*` CORS origin; `.env` is ignored by git; CI scans the history with gitleaks and audits Python dependencies with pip-audit | `config.py`, `.github/workflows/ci.yml` |
| Audit | Registration, sign-in, sign-out, refresh-token reuse, user and storage-site changes, lot creation and edits, recorded outcomes, rejected explanations | `services/audit.py` |

## Not done (needed before a real production use)

- The rate limiter keeps counters in process memory: with several instances, use a shared
  store (Redis) or the platform's limiter.
- No e-mail verification or password reset flow; an administrator re-creates access.
- No penetration test or external review has been performed.
- Backups and retention of PostgreSQL data depend on the hosting platform.
