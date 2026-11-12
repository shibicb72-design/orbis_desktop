# AGENTS.md - Orbis Desktop

Windows browser: Mozilla Firefox source at a pinned release tag, plus an Orbis overlay (branding, locked privacy
settings, scripts). Distributed only through the Microsoft Store as an MSIX. Sibling of Orbis for Android
(a separate repository: read-only from here).

## Ground rules

- One branch per ticket; PR body starts "Do not merge without Shibi's OK." Never merge without Shibi's OK, never
  force-push, never commit secrets.
- Workflow: one branch per PR. Push the branch and open the PR with `gh pr create`. The PR body starts "Do not
  merge without Shibi's OK." and is the only place the PR description lives. Agents never merge and never
  force-push.
- **Files on `C:` only** (owner's rule). The Firefox checkout and build output live outside the repository, by
  default under `%USERPROFILE%\orbis_desktop_src\`. Scripts must refuse any other drive.
- Delete nothing you did not create.
- No spending. No accepting licence terms. No installing software: list what is needed and its licence, and wait
  for Shibi's approval.
- English only. No servers, accounts, sync or analytics, in the product or in the tooling.
- Never install, uninstall or change settings on Shibi's PC (Developer Mode, certificates, Defender exclusions,
  default browser) without an explicit ask.
- Store identity and submissions belong to Shibi. Agents prepare packages and text; Shibi uploads and publishes.
  No Store credentials, Entra secrets or certificates in the repository or in agent-readable files.
- No Mozilla trademarks in the product: no "Firefox" or "Mozilla" in names, icons or UI text, except truthful
  attribution ("based on Mozilla's Firefox source code").
- Scripts must run in Windows PowerShell 5.1 (`powershell.exe`), not only PowerShell 7. Keep `.ps1` files ASCII.

## Project map

Items marked "planned" do not exist yet.

- `upstream/firefox.json`: the pinned Firefox tag **and** commit hash. The only place the version lives.
- `scripts/fetch-firefox.ps1`: shallow fetch of the pinned tag into `%USERPROFILE%\orbis_desktop_src\firefox` (or a
  given path); stops on a hash mismatch.
- `scripts/check-firefox-currency.ps1`: exits non-zero when Mozilla's latest release is newer than the pin, or when
  the pin is that release but still a `_BUILD` tag or not the commit of its `_RELEASE` tag.
- `docs/UPDATING.md`: how to move the pin to a new Firefox release.
- `patches/`: changes to Mozilla's files (`git apply` format, `-text` in `.gitattributes`). One row each in
  `docs/PATCHES.md` with the reason no setting could do it. Now: profile folder `Orbis` (`MOZ_APP_PROFILE`), the
  executables' version resource (company Orbis, no Firefox trademark line), the About dialog (no Mozilla
  community, donation, terms or privacy links) and no Mozilla `distribution.ini` in the MSIX.
- `scripts/apply-patches.ps1`: applies `patches/*.patch` to the pinned checkout after `git apply --check`; refuses
  a dirty tree, a wrong commit, or a checkout off `C:`. `-Check` writes nothing. Run it before `apply-overlay.ps1`.
- `scripts/apply-overlay.ps1`: copies the branding to `browser/branding/orbis/`, `mozconfig` to the checkout's
  top, and the policy files to `orbis-dist/` (install-folder layout, for packaging). Refuses any destination
  outside the checkout, through a junction, or tracked by Firefox's git, and refuses everything until
  `browser/moz.configure` sets `MOZ_APP_PROFILE` (patch 0001: the profile build blocker). It does not apply
  `patches/`.
- `scripts/make-placeholder-branding.ps1`: redraws the TODO placeholder images.
- `overlay/distribution/policies.json`: enterprise policies (feature switches, uBlock Origin, search engines).
- `overlay/orbis.cfg` + `overlay/defaults/pref/autoconfig.js`: locked and default prefs that no policy covers.
  `orbis.cfg` runs in AutoConfig's sandbox: pref functions only, and its first line is skipped by Firefox.
- `scripts/check-settings.py`: fails on unknown pref names, wrong pref types, invalid policies (checked against the
  pinned source's `policies-schema.json`) and settings missing from `docs/SETTINGS.md`.
- `overlay/browser/branding/orbis/`: name "Orbis"; icons and Store tiles are TODO placeholders. See
  `docs/BRANDING.md` for the trademark rules.
- `mozconfig`: Windows x64 release build options. `scripts/check-mozconfig.py` checks them against the source.
- `docs/BUILD.md`: build, package and check steps of the first build, and the packaging gap (`mach package` leaves
  out `orbis-dist`).
- `scripts/verify-build.py`: checks a built Orbis through Marionette (profile folder, prefs, policies, uBlock
  Origin, idle DNS lookups, About dialog). Needs a build and the Firefox checkout's Marionette client.
- `scripts/make-msix.ps1` + `packaging/msix-config.json`: unsigned MSIX from the packaged build with
  `mach repackage msix` (zip plus `orbis-dist`), then `makeappx unpack` checks of the manifest, assets and policy
  files. Store identity values are `TODO-STORE` placeholders (loud warning; `-RequireStoreIdentity` refuses
  them). Never signs or installs. See `docs/MSIX.md`.
- `docs/STORE-SUBMISSION.md`: Partner Center text (`runFullTrust` justification, certification notes), Store
  blockers, policy 10.2.1 engine currency, and policy risks.
- `docs/SETTINGS.md`: one row per setting: value, locked or default, reason, Firefox source; differences from
  Android.
- (planned) `tests/`: smoke tests (Marionette) and `network-allowlist.txt`.

## Design rules

- **The Firefox source is never edited by hand.** Every change is a file in `overlay/` or a patch in `patches/`.
  Prefer a policy or pref over a patch; every patch needs a line in `docs/PATCHES.md` saying why no setting could do it.
- **Never change a sandbox, process-model, JIT or add-on-signing default.** `MOZ_REQUIRE_SIGNING` stays on.
- Three layers, in this order of preference: build option (removes code), policy (named switch), AutoConfig pref.
- Every setting has a row in `docs/SETTINGS.md`. A setting without a reason does not merge.
- uBlock Origin is installed from addons.mozilla.org by policy. Never put an XPI in the repository or the package.
- The updater, crash reporter, default-browser agent and maintenance service are not built.
- Any new host in the network audit fails the build until it is added to the allow-list with a reason or blocked.

## Build and test

Available now:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-firefox-currency.ps1   # is the pin current?
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/fetch-firefox.ps1            # pinned source (large)
python -I scripts/check-mozconfig.py                                                      # mozconfig options vs the source
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/apply-patches.ps1 -Check     # do the patches apply?
python -I scripts/check-settings.py                                                       # prefs and policies vs the source
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/apply-overlay.ps1 -DryRun    # what would be copied
```

`check-settings.py` reads the checkout at `%USERPROFILE%\orbis_desktop_src\firefox` (or `--source DIR`). With only
the four source files it needs (see the script's header) it still runs, but prefs that no pref file defines then
fail, because it cannot search Firefox's code for them. `--ubo-assets FILE` also checks our uBlock Origin list set
against uBlock Origin's `assets.json`.

Planned:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1     # static checks, no Firefox needed
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build.ps1     # fetch, overlay, build, MSIX (about 1 hour)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke.ps1     # settings, uBlock Origin, network audit
```

Each prints `OK` or the first failure lines; full logs go to a `logs\` folder outside the repository (search them,
never read whole).

- Static checks will run on GitHub for every PR. The full build runs only on the build PC; GitHub's free runners are
  too small.
- CI actions are pinned to commit hashes.

## Engine currency

- `scripts/check-firefox-currency.ps1` fails when Mozilla's latest release is newer than `upstream/firefox.json`.
  (Planned: `.github/workflows/engine-currency.yml` runs it daily.)
- Build from the release-candidate tag (`FIREFOX_<n>_BUILD1`) as soon as it appears; submit to the Store with a
  publishing hold; publish on release day if the `_RELEASE` tag is the same commit.
- Store policy 10.2.1: never more than 2 major versions behind Firefox. The Orbis rule is much stricter (see README).
- A version bump PR changes `upstream/firefox.json` only, plus whatever the checks then demand (renamed prefs, a new
  host in the network audit, a patch that no longer applies). See `docs/UPDATING.md`.

## Delegation

- Builds and long test runs go to a subagent or a background script; the main conversation never reads build logs
  or anything under the Firefox checkout.
- Reviews: code, security and QA reviewers in parallel, as in the house workflow.
