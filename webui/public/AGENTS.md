# WebUI Public Assets DOX

## Purpose

- Own first-party static images, icons, splash art, Tamy branding assets, and PWA assets served by the WebUI.
- Keep visual assets stable for core UI surfaces and settings sections.

## Ownership

- `tamy-logo-icon.png` is the canonical selected Tamy brain/circuit mark used by the WebUI branding pass.
- `dark.svg` and `a0-fullDark.svg` expose the horizontal Tamy lockup for existing frontend references; `darkSymbol.svg` and `a0-collapsed.svg` expose the standalone symbol.
- `favicon.svg`, `favicon_round.svg`, `icon.svg`, and `icon-maskable.svg` expose Tamy application/PWA icons while keeping existing asset paths stable.
- Other SVG files own first-party icons and settings/category symbols.
- Raster files own splash, thumbnail, and app-icon imagery.
- Asset filenames are part of the frontend reference contract when used by HTML, CSS, JS, or plugins.

## Local Contracts

- Do not add secrets, user uploads, generated runtime files, or private user data here.
- Tamy brand assets are first-party product assets and must remain safe for repository distribution.
- Keep asset paths stable or update every frontend reference in the same change.
- Prefer optimized web formats and reasonable file sizes for assets loaded during startup.
- Preserve transparent logo edges and legibility on both dark and light UI surfaces.

## Work Guidance

- Use this folder for shared first-party assets, not component-specific images that belong with a plugin or component.
- Check contrast and legibility for icon changes in both light and dark UI contexts when relevant.
- Keep the startup/login/sidebar/PWA variants visually consistent with the canonical Tamy mark.

## Verification

- Manually smoke-test startup, login, expanded/collapsed sidebar, browser favicon, and installed PWA/app-icon surfaces after brand asset changes.
- Run frontend checks when asset references are covered by tests.

## Child DOX Index

No child DOX files.
