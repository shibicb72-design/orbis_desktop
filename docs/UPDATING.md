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

On exit code 1 the script also prints:

- the first release the pin lacks: the earliest release in `firefox_history_major_releases.json` and
  `firefox_history_stability_releases.json` that is newer than the pin (for a stale pin, the pinned version);
- Mozilla's release date of that release, and the Orbis deadline (that date + 3 days). A later release does not
  move the deadline: with the pin at 160.0, 160.0.1 on 2026-11-17 and 160.0.2 on 2026-11-24, the deadline is
  2026-11-20;
- how many major versions the pin is behind. At 2 it warns: Microsoft Store policy 10.2.1 allows at most 2.

If no history entry is newer than the pin (the feed has the new version before the history does), the date is
the feed's `LAST_RELEASE_DATE`. That date can be earlier than the real release date of a dot release, so the
deadline can come out early. That is the safe direction. If the history feeds fail, the date is "unknown" and the
exit code stays 1. `NEXT_RELEASE_DATE` is printed only if it is a plain `yyyy-mm-dd` date. `-ReportFile FILE`
writes the result as JSON.

## The daily check on GitHub

`.github/workflows/firefox-currency.yml` runs the check every day at 06:17 UTC, and on demand (Actions tab, "Firefox
currency", "Run workflow"). It runs on `windows-latest` with Windows PowerShell 5.1 (`shell: powershell`), because
the scripts use Windows paths. It uses only the workflow's `GITHUB_TOKEN` (`contents: read`, `issues: write`) and
the GitHub CLI that comes with the runner.

| Check result | What the workflow does |
|---|---|
| Behind or stale (exit 1) | Opens the issue **Firefox pin is out of date** with the label `firefox-update` (creates the label only if it is missing). If that issue is already open, it replaces the body and adds one comment, but only when something changed (new version, deadline passed). The issue lists the latest version, the first release the pin lacks and its release date, the 3-day deadline and the number of majors behind, with a Store 10.2.1 warning at 2 or more. The job stays green, with a warning |
| Current (exit 0) | Closes the open **Firefox pin is out of date** issue with a comment |
| Check failed (exit 2, or exit 1 without a report) | The job fails (red, with an error note). No issue is opened, changed or closed |

The issue is matched by its exact title and label. Other issues with the `firefox-update` label are never touched.
Do not edit the issue body: the next run overwrites it. Comment instead. The body contains no error text from
the feeds, so a feed hiccup does not change it.

The deadline is marked "(passed)" when the run's date, in UTC, is after it. Your local date can differ from the
UTC date, so the mark can be up to a day off.

A failed scheduled run sends an email only to the person who last changed the `cron` line, not to the repository
owner or watchers. Check the Actions tab, or change the `cron` line yourself, so that the emails come to you.

GitHub runs scheduled workflows only from the default branch, and turns them off in a public repository after 60
days without any commit. If that happens, the Actions tab shows a button to turn the workflow back on.

Test the check and the issue sync offline (local feed files, a throw-away git repository, canned GitHub CLI
output for 0, 1 and 2 open issues, no GitHub):

```
powershell -NoProfile -ExecutionPolicy Bypass -File tests\test-firefox-currency.ps1
```

`scripts\sync-currency-issue.ps1 -ReportFile FILE -Repository OWNER/NAME -DryRun` reads the open issues and labels
with `gh` (needs `gh auth login`) and prints each call that would change GitHub, with the issue text, instead of
running it. `-GhJson FILE` replaces those reads with canned output; the test uses it.

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
   python -I scripts\verify-build.py consent <install> <out>\cancel  cancel
   python -I scripts\verify-build.py consent <install> <out>\url     url
   ```

   All must end with `"result": "PASS"`. The `de-DE` runs simulate a Windows that is not in English, where
   `about:welcome` would otherwise offer a language pack from addons.mozilla.org. `url` checks that a start with
   a URL in between does not re-enable the Start-menu pin. `close`, `early`, `cancel` and `url`
   check that the screen comes back at the next start while uBlock Origin is neither declined nor installed. That
   relies on two things: Firefox treats an empty `browser.startup.homepage_override.mstone` as a new profile, and
   `browser.shell.disableStartMenuPin` stops the Start-menu re-pin. No release without them: a changed
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
