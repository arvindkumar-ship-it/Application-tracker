# Arvind's Job Portal

**Current delivery: Phase 1 foundation, awaiting live Docker acceptance. This is not the complete portal.**

The attached build specification requires every phase to pass its acceptance checks before the next phase starts. Docker is absent on the build machine. The Next.js frontend builds successfully; isolated authentication tests and offline migration compilation pass. Live PostgreSQL migration, real Redis login, worker health and the six-service Compose startup remain unverified. Phases 2–6 have not started.

## Included

- Next.js App Router, TypeScript, Tailwind and TanStack Query shell.
- Light warm-neutral UI, lavender primary actions, restrained peach, mint and soft blue accents. No fake jobs, profile details, metrics or resume claims.
- `/login`: password entry, visibility toggle, loading and failure states.
- `/`: protected foundation overview and real health response display. This is a foundation screen, not the final application dashboard.
- Mobile navigation, keyboard focus styles, reduced-motion support and desktop/mobile layouts.
- FastAPI password login/logout/me, signed 14-day httpOnly session, Redis-backed five-failure login limit, origin checks and structured errors.
- All 19 specification tables and exact enum values; UTC timestamps; a frozen initial Alembic migration.
- PostgreSQL 16, Redis 7, API, worker, beat and web Compose services. Container images and startup have not been tested here.
- Seven repeatable foundation unit tests. These mock Redis; they are not the specified full end-to-end suite.

Vault editing, fact generation, intake/extraction/review, job tracking, Google Sheets sync and resume tailoring are **not implemented**. Their navigation entries are explicitly unavailable. No buttons pretend to complete those workflows.

## Windows setup

Install and start Docker Desktop with Linux containers before using these commands. Open PowerShell in this folder.

```powershell
Copy-Item -LiteralPath .env.example -Destination .env
docker compose version
```

Generate a password hash using the backend image. The password prompt does not echo and the password is not included in shell history. Save the printed hash into `APP_PASSWORD_HASH` in `.env`. **Enclose the entire hash in single quotes** so Compose does not expand its dollar characters.

```powershell
docker compose build api
docker compose run --rm --no-deps api python -c 'from getpass import getpass; from app.security import hash_password; print(hash_password(getpass("Workspace password (12+ characters): ")))'
docker compose run --rm --no-deps api python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Save the second output as `SESSION_SECRET`. Do not keep the example secret. Keep `.env` private and untracked. No default password is supplied.

`DATABASE_URL` and `REDIS_URL` defaults use Docker service hostnames. `NEXT_PUBLIC_API_URL=http://localhost:8000/api` is embedded during the web image build. Open the frontend using **localhost**, consistently, at [http://localhost:3000](http://localhost:3000). The development CORS origin is exactly `http://localhost:3000`. Ports bind only to the local machine.

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod -Uri http://localhost:8000/api/health
docker compose logs --tail 80 api worker web
```

The API applies migrations before listening. Sign in at [http://localhost:3000/login](http://localhost:3000/login). Verify login, reload, logout and rejected unauthenticated requests. Database, Redis and worker health must be true. External configuration flags are reported separately and must never be described as successful API connectivity tests.

`ANTHROPIC_API_KEY` and `LLM_MODEL` can remain empty during infrastructure verification; LLM functionality is not built yet. The final product requires a real configured model and key. No SDK calls or invented extracted data are present in this phase.

For password reset, generate another hash, update `.env`, and recreate the API. Rotating `SESSION_SECRET` invalidates existing sessions.

```powershell
docker compose up -d --force-recreate api
```

The backend uses secure cookies when its configured API URL is HTTPS. Production requires HTTPS and an origin/reverse-proxy deployment plan; the current Compose configuration is for local use.

## Checks

```powershell
docker compose run --rm --no-deps -v "${PWD}/backend/tests:/app/tests:ro" api python -m unittest discover -s tests -v
docker compose exec api alembic current
docker compose exec api alembic upgrade head
docker compose exec web node --version
```

For a frontend-only local preview with Node.js 22 or later:

```powershell
Set-Location frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

The frontend needs the real backend for authentication. No preview password or authentication bypass is shipped. Without the API, `/login` renders and submits a clear connection error. The visual review used a separate scratch server with mocked login storage; that server is not part of this deliverable.

## Phase 1 acceptance record

| Check | Result |
|---|---|
| Production frontend build | Passed |
| TypeScript checking | Passed in production build |
| Seven foundation unit tests | Passed; Redis mocked |
| All 19 tables register | Passed |
| Alembic offline upgrade/downgrade | Passed; 19 tables, 21 enum types |
| PostgreSQL applies migration on empty DB | Blocked: Docker unavailable |
| Six Compose services start | Blocked: Docker unavailable |
| Real Redis login and worker ping | Blocked: Docker unavailable |
| External LLM/Sheets connection | Not implemented or tested |
| Phase 1 complete | **No** |

Visual review covered both implemented routes (`/login`, `/`) at desktop and 390px mobile, including drawer navigation and lower-page content. Supporting text was enlarged and its contrast increased. Health failures were given explicit offline states. Final whole-product visual sign-off remains pending until all specified routes exist.

## File-to-acceptance map

| Files | Acceptance contribution |
|---|---|
| `docker-compose.yml`, both `Dockerfile`s, `.env.example`, `.gitignore` | Six-service infrastructure, build and secret separation |
| `backend/pyproject.toml` | Backend runtime dependency installation |
| `backend/app/config.py`, `db.py` | Startup configuration validation, UTC async PostgreSQL connection |
| `backend/app/security.py`, `deps.py`, `api/auth.py` | Password verification, sessions, auth guards and login limits |
| `backend/app/main.py`, `api/health.py`, `tasks/celery_app.py` | App routing, standard errors, health and worker connectivity |
| `backend/app/models/base.py`, `vault.py`, `intake.py`, `job.py`, `tailoring.py`, `sync.py`, `__init__.py` | All specified tables, relationships and enums |
| `backend/alembic.ini`, `alembic/env.py`, `alembic/versions/0001_foundation.py` | Initial migration and offline/online migration entry points |
| `backend/tests/test_api_flow.py` | Isolated foundation security and schema checks |
| Frontend package/lockfile, TS/Next/Tailwind/PostCSS configs | Reproducible install, type checking and production build |
| `frontend/src/app/layout.tsx`, `globals.css`, `components/AppShell.tsx` | Providers, auth gate, light design system and responsive navigation |
| `frontend/src/app/login/page.tsx`, `app/page.tsx` | Sign-in and protected health overview |
| `frontend/src/lib/api.ts`, `types.ts` | Cookie-based typed API calls and error normalization |

## Google Sheets preparation for Phase 4

Create a Google Cloud project, enable Google Sheets API, create a service account and download its JSON key to a private location outside this repository. Create a Sheet and share it as Editor with the JSON key's `client_email`. Phase 4 will mount that private file at `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`, add the actual Settings screen and implement connection testing, push, pull and conflict handling. The current Compose file intentionally has no key mount because it is not used in Phase 1.

## Backup

Once the database is running, this PowerShell command writes a custom-format PostgreSQL backup without binary output redirection:

```powershell
docker compose exec -T db pg_dump -U portal -d portal -Fc -f /tmp/portal.dump
docker compose cp db:/tmp/portal.dump ./portal-backup.dump
```

Uploaded files and resumes will live in the `portal_data` volume under `/data`. Back up that volume separately before production use. No uploaded files or generated resumes exist in this foundation delivery.
