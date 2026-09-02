# Settings Components DOX

## Purpose

- Own WebUI settings shell and built-in settings subsections.

## Ownership

- `settings.html` and `settings-store.js` own the settings shell and state.
- Subdirectories own settings areas such as agent, external, developer, MCP, backup, plugins, secrets, skills, tunnel, and A2A.
- `developer/developer-hub.html` and `developer/developer-hub-store.js` own the Super Admin Developer Hub GitHub console, including connection state, changed-file selection, push review, synchronization controls, and audit display.
- `mcp/client/` owns the global/project MCP server manager, server search, raw JSON editor surface, examples modal, server tool detail modal, MCP scanner modal, scan checks, and scan prompt assets.
- `skills/` owns skill listing, importing, standalone skill scanning, uploaded archive scan preparation UI, scanner modal, scan checks, and scan prompt assets.

## Local Contracts

- Keep settings payloads synchronized with backend APIs and plugin settings contracts.
- Settings tabs that expose plugin `settings_sections` must mount `settings/plugins/plugins-subsection.html` with matching `data-tab` and sidebar/nav section IDs.
- Do not store secrets in localStorage, URLs, or console output.
- Preserve Store Gating and modal footer conventions in settings components.
- Tamy Developer Hub must never persist or render a GitHub token in frontend state after Connect completes; backend authorization remains the source of truth for all Git mutations.
- Tamy Developer Hub review state is disposable: selection, commit-message, refresh, or backend errors invalidate the previous push fingerprint.
- Interface control visibility is edited as a Save/Cancel draft, persisted with instance settings, and applied through the shared frontend preference store after Settings saves successfully.
- Bundled controls contributed by plugins add their Interface row through
  `interface-controls-end` and register visibility defaults with the shared
  preference store.
- MCP manager tool toggles write `disabled_tools` into the draft JSON and require Apply before changing the running MCP tool set.
- Confirmed MCP server removals apply immediately and refresh server status; other MCP manager draft edits still require Apply.
- MCP manager local command forms accept shell-style command and argument lines; quote argument values that intentionally contain spaces.

## Work Guidance

- Prefer subsection-local stores for complex settings areas.
- Coordinate plugin settings UI changes with `webui/components/plugins/` and `plugins/AGENTS.md`.
- Keep Developer Hub GitHub mutation logic in the backend service; the browser only submits bounded actions and review inputs.
- Keep MCP scanner checks and prompt assets close to the MCP client modal so scanner behavior remains reviewable with the UI that invokes it.
- Keep Skills scanner checks and prompt assets close to the Skills settings section so scanner behavior remains reviewable with import and standalone scan entry points.
- Keep MCP manager search and toggle affordances consistent between global and project scope because both are rendered by the same client modal.

## Verification

- Smoke-test changed settings tabs, Interface mobile/desktop selectors, and save/reload behavior after visible or API changes.
- For Developer Hub changes, verify GitHub Connect/Disconnect, local status, changed-file selection, stale review blocking, secret blocking, fast-forward pull, sync, audit log, and mobile layout.

## Child DOX Index

No child DOX files.
