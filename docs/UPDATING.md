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

It reads `LATEST_FIREFOX_VERSION` from https://product-details.mozilla.org/1.0/firefox_versions.json.

| Exit code | Meaning |
|---|---|
| 0 | The pin equals or is ahead of Mozilla's latest release |
| 1 | `BEHIND`: Mozilla has a newer release. Update the pin |
| 2 | The check failed (network, feed format, pin file). Treat as a failure too |

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
5. Open a version bump PR that changes `upstream/firefox.json` only, plus whatever the later checks demand.

To build a release candidate before release day, pin `FIREFOX_<n>_BUILD<k>` the same way. On release day, check
that `FIREFOX_<n>_RELEASE` is the same commit, then switch the tag in the pin.

## If the fetch refuses

`REFUSED` means the tag does not point at the pinned commit. Do not edit the pin to make the error go away. First
find out why: a typo in the pin, Mozilla moving a tag (rare), or something between this PC and GitHub. If a
refused fetch left a wrong tag in the checkout, delete that checkout folder and fetch again.
