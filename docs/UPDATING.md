# Updating the pinned Firefox

Orbis is built from one exact Firefox release. `upstream/firefox.json` names it:

| Field | Meaning |
|---|---|
| `repository` | Where the source comes from: https://github.com/mozilla-firefox/firefox |
| `tag` | The Firefox tag, for example `FIREFOX_160_0_RELEASE`. The version (160.0) is read from the tag |
| `commit` | The full commit SHA the tag must point at. Scripts refuse anything else |
| `verified` | When and how the tag and commit were checked |

## Is the pin current?

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-firefox-currency.ps1
```

It reads `LATEST_FIREFOX_VERSION` from https://product-details.mozilla.org/1.0/firefox_versions.json. When
the pinned version equals it, the script also runs `git ls-remote` on `FIREFOX_<version>_RELEASE` and checks that
the tag points at the pinned commit.

| Exit code | Meaning |
|---|---|
| 0 | The pin equals or is ahead of Mozilla's latest release |
| 1 | `BEHIND`: Mozilla has a newer release. Update the pin |
| 1 | `STALE`: the pin is Mozilla's latest version but is still the `_BUILD` tag, or the `_RELEASE` tag is a different commit. Switch the pin to the `_RELEASE` tag and its commit |
| 2 | The check failed (network, git, feed format, pin file). Treat as a failure too |

## Move the pin to a new release

1. Find the tag and its commit:

   ```
   git ls-remote https://github.com/mozilla-firefox/firefox "refs/tags/FIREFOX_161_0_*"
   ```

   A line ending in `^{}` is the commit of an annotated tag; use that SHA. Without such a line the tag points
   directly at the commit.
2. Edit `upstream/firefox.json`: `tag`, `commit` (all 40 characters, lower case) and `verified`.
3. Run `scripts\check-firefox-currency.ps1`. It must print `OK`.
4. Fetch the source (several GB the first time):

   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch-firefox.ps1 [-Destination C:\path\to\firefox]
   ```

   Default destination: `%USERPROFILE%\orbis_desktop_src\firefox`. The destination must be on `C:` and outside this
   repository. The script checks the tag on the remote **before** downloading, fetches only that tag with depth 1,
   checks the fetched commit again, and only then checks it out. Any mismatch prints `REFUSED` and exits 1.
   Running it again on the same folder is safe.
5. Check that the source patches still apply (writes nothing):

   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-patches.ps1 -Check
   ```

   If a patch no longer applies, rebase it by hand on the new source (see `docs/PATCHES.md`).
6. Check the prefs, the policies and the uBlock Origin consent screen against the new source:

   ```
   python -I scripts\check-settings.py
   ```

   Besides prefs and policies, it checks that the new source's `about:welcome` still has everything the consent
   screen uses (`checkedAction`, `uncheckedAction`, `uncheckedNotice`, `collectSelect`, `INSTALL_ADDON_FROM_URL`,
   `OPEN_ABOUT_PAGE` with `home`, the language-mismatch and campaign-action switches), and that no policy Orbis
   uses has started to switch `about:welcome` off. If Firefox drops or renames one of them, `about:welcome` may
   ignore Orbis's screens and show Mozilla's full onboarding instead, so this check must pass.
7. **Required gate, on every bump:** build, then run the consent test on the new build (`docs/BUILD.md`, step 5),
   both ways:

   ```
   python -I scripts\verify-build.py consent <install> <out>\accept  accept
   python -I scripts\verify-build.py consent <install> <out>\decline decline
   python -I scripts\verify-build.py consent <install> <out>\accept-de  accept  --system-locale de-DE
   python -I scripts\verify-build.py consent <install> <out>\decline-de decline --system-locale de-DE
   python -I scripts\verify-build.py consent <install> <out>\close   close
   python -I scripts\verify-build.py consent <install> <out>\close-de close  --system-locale de-DE
   python -I scripts\verify-build.py consent <install> <out>\early   early
   ```

   All must end with `"result": "PASS"`. The `de-DE` runs simulate a Windows that is not in English, where
   `about:welcome` would otherwise offer a language pack from addons.mozilla.org. `close` checks that a screen
   left unanswered comes back at the next start (it relies on Firefox treating an empty
   `browser.startup.homepage_override.mstone` as a new profile). No release without them: a changed
   `about:welcome` could install uBlock Origin without consent, show Mozilla's onboarding, stop asking again, or
   contact addons.mozilla.org before the user answers.
8. Open a version bump PR that changes `upstream/firefox.json` only, plus whatever the later checks demand. Paste
   the consent results into the PR.

To build a release candidate before release day, pin `FIREFOX_<n>_BUILD<k>` the same way. On release day, check
that `FIREFOX_<n>_RELEASE` is the same commit, then switch the tag in the pin.

## If the fetch refuses

`REFUSED` means the tag does not point at the pinned commit. Do not edit the pin to make the error go away. First
find out why: a typo in the pin, Mozilla moving a tag (rare), or something between this PC and GitHub. If a
refused fetch left a wrong tag in the checkout, delete that checkout folder and fetch again.
