# Verification record

- 26 backend tests passed; 1 external-model test skipped because Anthropic key/model are absent.
- 4 frontend component tests passed.
- Production Next.js compilation, type checks, page generation and standalone packaging passed. Build uses one worker and disables production webpack disk caching to reduce peak memory/disk needs on this machine.
- Integration test uses an isolated SQLite compatibility adapter, not production PostgreSQL. It checks the full manual/labelled intake and verified resume flow, selectable one-page PDF, DOCX text, exact PNG PDF preview, valid/invalid bullet edits, re-render/final marking, status history, CSV, fact citation preservation, soft delete and fake remote Sheet append/pull/conflict/idempotence/recovery.
- Twelve explicitly synthetic text/HTML/PNG/PDF fixtures are included for the external extraction run. They are not owner job data.
- Browser QA used an isolated local test database. Profile/project save, source splitting, fact confirmation, intake approval, inline status save, resume generation and an actual rendered PDF image were verified through the UI.
- Desktop and 390px mobile review covered login, dashboard, Vault, deep project, new intake, review, Master List, job detail, resume tailoring and Settings. Issues fixed included raw-JSON link editing, empty-list confidence, repeated primary controls, mobile mode-tab wrapping, search sizing, field names, source review states, empty resume section headings and black PDF iframe previews.
- Current Docker deployment has NOT been replaced by these source changes. Docker CLI execution remains denied to this Codex sandbox. Run `docker compose up --build -d` from this project folder to build/install the update; keep `.env` and volumes.
- Live Anthropic OCR/extraction/rewriting and Google Sheets API authorization/quota behavior remain unverified without credentials. The app displays this configuration state and offers exact-label/manual review and verified-fact resume mode instead of fake success.
- New migration `0002_job_soft_delete` was checked offline; updated-image PostgreSQL migration/concurrency and real worker execution require the Docker update. The original foundation's live health was previously green.
- No owner profile/job facts were fabricated or seeded into the live database. No API keys, private service-account keys or local `.env` are included in the source archive or GitHub update.
