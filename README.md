# Arvind's Job Portal

Private, single-owner job workspace built with Next.js, FastAPI, PostgreSQL, Redis and Celery. Light neutral UI with lavender, peach, mint and soft blue accents.

## Update the running portal

From this project folder in PowerShell:

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/api/health
```

Keep your existing `.env` and Docker volumes. Do not reset the database or copy `.env.example` over a configured `.env`. The API applies Alembic migrations before listening, including the job soft-delete migration. Open http://localhost:3000/login using the password you configured.

The previous foundation image does not acquire new features until it is rebuilt. This delivery's updated container build/start still needs to be executed on Docker Desktop: this Codex sandbox cannot execute the Docker CLI. Earlier foundation health showed database, Redis and worker online; that does not certify the updated images.

## Working workflows in source

- Dashboard with live application counts, review queue, next-seven-day deadlines, due follow-ups and missing verified-fact warnings.
- Vault: profile, education, experience, deep projects, project technologies, skills/aliases, achievements, publications, certifications and five editable resume layouts. Profile links have a normal link editor.
- Facts: add atomic claims, split exact source sentences into candidates, edit/verify and supersede. Unverified facts and disallowed skills are excluded from tailoring. Cited facts cannot be overwritten; replacement preserves the original evidence.
- Intake: public URL, pasted text, reordered screenshots or PDF. Upload limits and file signatures are validated. Public URL fetches validate/pin destination IPs and reject private addresses and unsafe redirects. Blocked sources request manual text.
- Review: evidence quotes, confidence/unknown states, editable source, re-extraction, duplicate confirmation, discard and explicit approval. Title/company are required. Approval is idempotent and transactional.
- Master List: search, status/priority/work-mode/deadline filters, sortable columns, column visibility, inline status/dates/notes, pagination, CSV export, job details, evidence and status history. Setting Applied fills today's date in Asia/Kolkata when empty. Soft deletion preserves source/history/resumes and marks the Sheet note.
- Google Sheets: exact A:AG headers, Job-ID upserts, dropdowns, five-minute pending/failed push retry, explicit pull, three-way comparison, invalid-value rejection, missing-row recovery and keep-app/take-Sheet conflict resolution.
- Resumes: per-job layout/page/summary/emphasis controls, verified evidence selection, conservative bullet validation, honest coverage, exact PDF-page previews, selectable PDF and DOCX exports, version history, manual bullet revalidation and final-version selection. Page fitting removes low-priority bullets instead of shrinking fonts below the template minimum.

## What works without external credentials

Pasted jobs with explicit labels such as `Company:`, `Role:`, `Required skills:` and `Salary:` are copied exactly into review fields. Unlabelled/unknown fields can be entered manually. This deterministic mode is clearly identified and does not pretend to be automatic LLM extraction.

Facts are split as exact source sentences and remain unverified until you confirm them. With no LLM key, resumes use exact eligible action statements, not fabricated rewrites. Confirm specific facts beginning with an action verb and keep each to 28 words or fewer. Unsupported keywords are listed honestly; no candidate match score is used.

## Enable automatic extraction and rewriting

Set these only in local `.env`:

```dotenv
ANTHROPIC_API_KEY=your-local-key
LLM_MODEL=your-enabled-model-id
```

Then recreate API/worker/beat:

```powershell
docker compose up -d --force-recreate api worker beat
```

All LLM SDK calls are isolated in `backend/app/llm/client.py`. Prompts treat source material as untrusted data. Outputs are schema-validated, evidence-checked and conservatively claim-validated. Valid paraphrases may be rejected if their wording cannot be proven against cited facts; dropped bullets are reported rather than invented.

Screenshots and scanned PDFs require the model's vision capability. Text PDFs can be read without OCR. No model/key is supplied with this repository.

## Enable Google Sheets

1. Create a service account in your Google Cloud project and enable Google Sheets API. Keep its JSON key outside this repository.
2. Set `GOOGLE_SERVICE_ACCOUNT_JSON_PATH=/data/service-account.json` in `.env`.
3. Copy the key into the shared data volume, substituting the real key file path:

```powershell
docker compose cp YOUR_KEY_FILE.json api:/data/service-account.json
docker compose up -d --force-recreate api worker beat
```

4. Share your Sheet as Editor with the key's `client_email`.
5. Open Settings, save the Sheet ID and tab name, then Test connection. Use an empty tab; mismatched headers are never silently overwritten.

Approval and local tracking do not depend on Sheets availability. Failed/pending sync is visible. Private keys and API credentials are never stored in app settings, committed or displayed.

## Fresh setup only

Install/start Docker Desktop in Linux-container mode. For an unconfigured checkout only:

```powershell
Copy-Item .env.example .env
docker compose build api
```

Generate a random session secret locally and save it as SESSION_SECRET. Configure your password without displaying it or its hash:

```powershell
docker compose run --rm --no-deps -v "${PWD}:/setup" api python /setup/backend/app/security.py
```

Enter the same 12+ character password twice. The helper writes a single-quoted PBKDF2 hash to prevent Compose interpolation of dollar characters. Existing valid hashes are preserved. This helper expects a configured random SESSION_SECRET; do not retain the example placeholder.

## Verification performed

- Production frontend compilation and type checks passed during development; final rebuild results are recorded in the delivery report.
- 26 backend tests passed; one external golden-extraction test covering 12 synthetic fixtures is skipped without an Anthropic key/model.
- Four frontend component tests passed: evidence editing, unknown confidence, grid inline editing and honest coverage.
- Integration test exercises real routes/services against an isolated SQLite adapter: profile/project/fact creation and confirmation; labelled text intake; approval idempotence; master/status history; CSV; one-page selectable PDF and DOCX; invalid bullet rejection; valid edit/re-render; final marking; fake remote Sheet append/idempotence/pull/conflicts/invalid values/deleted-row recovery; job soft deletion.
- PostgreSQL concurrency, actual Google API credentials/quota behavior, live Anthropic OCR and the twelve external-model fixtures still require deployment-specific checks. The SQLite adapter is test-only and never replaces production PostgreSQL.
- Browser review used isolated synthetic QA data, never the owner's database. Main routes were reviewed at desktop and 390px mobile; visual corrections included readable supporting text, duplicate-action removal, clean links, corrected unknown badges, mobile forms and actual PDF-page previews.

Run the shipped checks:

```powershell
docker compose run --rm --no-deps api python -m unittest discover -s tests -v
Set-Location frontend
npm ci
npm test
npm run build
```

Tests use a separate temporary database and generated credentials. Fixtures are explicitly synthetic; none are inserted into the owner's database. The full external-model test is skipped when configuration is absent, never reported as passed.

## Storage and backups

Production data stays in the existing PostgreSQL Docker volume. Uploaded sources and resume files are in `portal_data` at `/data`. Times are stored in UTC and displayed in Asia/Kolkata. Local ports bind to 127.0.0.1. Production internet exposure requires HTTPS and an origin/reverse-proxy deployment plan.

```powershell
docker compose exec -T db pg_dump -U portal -d portal -Fc -f /tmp/portal.dump
docker compose cp db:/tmp/portal.dump ./portal-backup.dump
```

Back up `/data` separately. Never use `docker compose down -v` when preserving your data. This application does not auto-apply to jobs, scrape job boards or provide multi-user signup.
