# GitHub Automation DOX

## Purpose

- Own repository automation that runs on GitHub, including workflows and release-planning scripts.
- Keep CI, Docker publishing, stale issue handling, release-note generation, Tamy branding automation, and focused Developer Hub validation aligned with repository rules.

## Ownership

- `workflows/` contains GitHub Actions workflow definitions.
- `branding/` contains compact source assets used by branding automation.
- `scripts/` contains Python helpers called by workflows.
- This file owns release, branding, and focused validation automation rules; user-facing release documentation belongs under `docs/`.

## Local Contracts

- Docker publishing lives in `workflows/docker-publish.yml` and delegates planning to `scripts/docker_release_plan.py`.
- `workflows/brand-tamy.yml` owns the repeatable frontend white-label pass for Tamy. It reads the selected logo source from `branding/tamy-logo-icon.b64`, writes the first-party WebUI identity assets, applies the Tamy name and palette to user-facing surfaces, verifies required assets, and commits only tracked frontend branding changes.
- `workflows/validate-tamy-developer-hub.yml` compiles the Developer Hub backend and runs its isolated security/helper tests whenever the Hub backend, UI, tests, or workflow changes.
- Keep invisible runtime compatibility identifiers unchanged when branding the UI unless the owning runtime contract is intentionally migrated at the same time.
- Releasable tags are `vX.Y` tags at or above `v1.0`, matching the workflow environment.
- On `main`, the newest eligible tag publishes both the version tag and `latest`, then creates or updates its GitHub release after the image push succeeds; other allowed branches publish only their branch tag.
- Manual dispatch without a tag backfills missing Docker Hub tags. Manual dispatch with a tag rebuilds that target and refreshes `latest` and the GitHub release only when it remains the newest eligible tag on `main`.
- Release-note generation reads `scripts/openrouter_release_notes_system_prompt.md` from the repository root and requires OpenRouter credentials from workflow environment variables.
- Release notes compare against the previous published GitHub release tag and fall back to `No release notes.` when no meaningful summary is generated.
- Keep workflow secrets in GitHub Actions secrets or environment variables. Do not commit credentials, tokens, or generated release bodies containing private data.
- Workflow scripts must fail loudly with actionable messages when required environment variables or git refs are missing.

## Work Guidance

- Prefer deterministic, testable Python for workflow planning logic instead of complex inline shell in YAML.
- Preserve manual dispatch behavior when changing Docker publishing or branding workflows.
- Keep branch, tag, release, branding, and focused validation behavior synchronized between workflow YAML, source assets, tests, and user-facing documentation where applicable.

## Verification

- Run `pytest tests/test_docker_release_plan.py` after changing Docker publish planning or release workflow behavior.
- For `brand-tamy.yml`, verify the workflow completes successfully and then inspect the startup, login, sidebar, favicon/PWA assets, and `branding.css`/`branding.js` outputs on `main`.
- For `validate-tamy-developer-hub.yml`, require Python compile and `pytest -q tests/test_tamy_developer_hub.py` to pass.
- Run targeted tests for any changed script that already has coverage.

## Child DOX Index

No child DOX files.
