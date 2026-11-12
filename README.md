# Orbis Desktop

Orbis Desktop is a private web browser for Windows. It is the desktop sibling of Orbis for Android.

**Status: pre-release.** Nothing has been published yet: there is no release build and no Microsoft Store listing.
The features below describe the target, not a finished product.

## What it is

- **Built from Firefox source code.** Orbis Desktop is built from Mozilla's Firefox source code. Orbis adds its own
  name, icons and privacy settings, leaves out the updater, crash reporter and default-browser agent, and may carry
  a small number of patches to Mozilla's files. Every change is in this repository.
- **Not affiliated with Mozilla.** Orbis Desktop is not made by, endorsed by, or affiliated with Mozilla.
- **No Firefox trademarks.** The browser does not use the Firefox or Mozilla names or logos. The only mention is the
  truthful attribution "based on Mozilla's Firefox source code". Firefox and Mozilla are trademarks of the Mozilla
  Foundation. Microsoft and Windows are trademarks of the Microsoft group of companies.
- **Microsoft Store only.** Orbis Desktop is distributed and updated only through the Microsoft Store. There is no
  other download and no built-in updater.
- **No servers, accounts, sync or analytics.** Orbis's developer runs no servers and receives nothing. There are no
  Orbis accounts, no sync, no telemetry and no analytics.
- **English only.**

## What it does

- Blocks ads and trackers with uBlock Origin, installed automatically from addons.mozilla.org on first run.
- Strict tracking protection and per-site cookie isolation on every tab.
- HTTPS-only mode on by default.
- No telemetry, no studies, no crash reports, no accounts, no sync, no sponsored content, no AI chat.

Malware and phishing protection: Orbis blocks known malware and phishing sites with open blocklists in uBlock
Origin. It does not use Google Safe Browsing, so it sends nothing to Google, but it catches new phishing pages
later than Chrome or Firefox do. Orbis does not change Windows SmartScreen. Every setting and its reason
is in `docs/SETTINGS.md`.

## What leaves your PC

A full list will be in `PRIVACY_POLICY.md` (TODO). In short: the sites you visit, your chosen search engine,
addons.mozilla.org and filter-list publishers (uBlock Origin), Mozilla (security lists, push service, media
plugins and translation models), Cisco (the OpenH264 video codec), certificate authorities (revocation checks), and
the Microsoft Store (updates). Nothing goes to Orbis's developer. Each call and its reason is listed in
`docs/SETTINGS.md`, "Network calls that remain".

## How this repository works

This repository does **not** contain Firefox. It contains a small overlay that is applied to an exact Firefox
release. Paths marked "planned" do not exist yet.

| Path | What |
|---|---|
| `upstream/firefox.json` | The Firefox release tag and commit that Orbis is built from |
| `scripts/` | Fetch the pinned Firefox source, check that it is current, check the settings and mozconfig, apply the patches and the overlay; later: build, package, test |
| `overlay/` | Files copied into the Firefox build: the policy files (`distribution/policies.json`, `orbis.cfg`, `defaults/pref/autoconfig.js`) and the Orbis branding (`browser/branding/orbis/`, placeholder art) |
| `patches/` | Changes to Mozilla's own files, kept as few as possible; each one explained in `docs/PATCHES.md` |
| `mozconfig` | Build options (Windows x64, release; no updater, crash reporter or telemetry reporting) |
| `docs/` | Update guide, settings rationale, patches, branding rules; later: build guide, network audit, Store materials |
| `tests/` | (planned) Smoke tests and the network allow-list |

Every difference between Orbis and Firefox is in this repository.

## Building

TODO: `docs/BUILD.md`. The build runs on Windows with Mozilla's MozillaBuild environment and needs about 40 GB of free
disk space. The Firefox source and all build output live outside this repository (by default under
`%USERPROFILE%\orbis_desktop_src\`).

## Updates and security

Firefox ships every two weeks, plus unplanned security fixes. Orbis follows each release.

TODO (promise wording decision): the exact update promise.

`scripts/check-firefox-currency.ps1` fails when the pinned Firefox version is behind Mozilla's latest release. See
`docs/UPDATING.md`.

## Source code and licences

- Orbis's own files: Mozilla Public License 2.0, see `LICENSE`.
- Firefox source: https://github.com/mozilla-firefox/firefox at the tag and commit named in `upstream/firefox.json`,
  MPL-2.0, with third-party components listed in the browser at `about:license`.
- uBlock Origin is GPL-3.0. Orbis does not include it; your browser downloads it from addons.mozilla.org.

## Reporting a security problem

TODO: contact route (to be chosen by the owner).
