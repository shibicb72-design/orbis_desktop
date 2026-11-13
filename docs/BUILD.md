# Building and checking Orbis Desktop

How the first Orbis build (Firefox 160, 2026-11-12) was built, packaged and checked, step by step, and the one gap
found: `mach package` leaves out Orbis's policy files. The planned `scripts/build.ps1` and `scripts/smoke.ps1` will
run these steps; until then, run them by hand on the build PC.

Paths below use the defaults: Firefox checkout `%USERPROFILE%\orbis_desktop_src\firefox`, build output
`%USERPROFILE%\orbis_desktop_src\obj-orbis` (`MOZ_OBJDIR` in `mozconfig`). Everything stays on drive C:.

## Needed on the build PC

- MozillaBuild in `C:\mozilla-build`, and the toolchains that `./mach bootstrap` installs in `%USERPROFILE%\.mozbuild`.
  Both were already installed on the build PC; this document installs nothing.
- Python 3 on the PATH for `scripts/check-*.py` and `scripts/verify-build.py`.

## 1. Source, patches, overlay

From the Orbis repository, in Windows PowerShell:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch-firefox.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-patches.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-overlay.ps1
python -I scripts\check-mozconfig.py
python -I scripts\check-settings.py
```

`apply-patches.ps1` refuses a checkout that has only some of the patches applied (for example the first build's
checkout, which has 0001 and 0002 but not 0003). Undo them first with the `git checkout` line in
`docs/PATCHES.md`, then run it again.

`apply-overlay.ps1` copies the branding to `browser\branding\orbis`, `mozconfig` to the top of the checkout, and
the policy files to `orbis-dist\` in the checkout:

```
orbis-dist\orbis.cfg
orbis-dist\defaults\pref\autoconfig.js
orbis-dist\distribution\policies.json
```

## 2. Build

`mach` runs in MozillaBuild's MSYS2 shell. The first build started it from PowerShell like this, with a clean
environment (variables that break MozillaBuild removed) and the checkout's `mozconfig`:

```
foreach ($v in 'CYGWIN','INCLUDE','LIB','GITDIR','PYTHON','PYTHONPATH','MSYSTEM_PREFIX','MINGW_PREFIX') {
    Remove-Item "Env:$v" -ErrorAction SilentlyContinue }
$env:MOZILLABUILD = 'C:\mozilla-build\'
$env:MSYSTEM = 'MSYS'
$env:MSYS2_PATH_TYPE = 'inherit'
$env:CHERE_INVOKING = '1'
$env:MOZCONFIG = "$env:USERPROFILE\orbis_desktop_src\firefox\mozconfig"
& 'C:\mozilla-build\msys2\usr\bin\bash.exe' -l build.sh
```

`build.sh`:

```
cd "$(cygpath "$USERPROFILE")/orbis_desktop_src/firefox" || exit 1
export MACH_HIDE_DEV_DRIVE_SUGGESTION=1
./mach build > ../build-orbis.log 2>&1 < /dev/null
```

The first build took 47 minutes (2848 s) and ended with exit code 0. The full log is under
`obj-orbis\.mozbuild\logs\build\`; search it, do not read it whole.

## 3. Package

Same shell setup, with `package.sh`:

```
cd "$(cygpath "$USERPROFILE")/orbis_desktop_src/firefox" || exit 1
export MACH_HIDE_DEV_DRIVE_SUGGESTION=1
./mach package > ../package-orbis.log 2>&1 < /dev/null
```

It took 2 minutes and writes, in `obj-orbis\dist\`:

- `orbis-160.0.en-US.win64.zip`: the application, in a top-level `orbis\` folder;
- `install\sea\orbis-160.0.en-US.win64.installer.exe`: Firefox's NSIS installer. Not used: Orbis ships only as
  MSIX;
- `win64\xpi\orbis-160.0.en-US.langpack.xpi`: an en-US language pack. Not used (`docs/BRANDING.md`).

## 4. The packaging gap: Orbis's policy files are not in the package

`mach package` copies only the files that `browser/installer/package-manifest.in` lists. `orbis-dist\` is not
part of the build, so the zip has no `orbis.cfg`, no `defaults\pref\autoconfig.js` and no
`distribution\policies.json`. Started from the zip as it is, Orbis runs **without** its locked settings, its
policies and uBlock Origin: a plain Firefox with Orbis branding. (The zip's only file under `defaults\pref` is
`channel-prefs.js`, and it has no `distribution` folder: checked on the first build's zip.)

### What the first build did: add the files after packaging

```
$dist = "$env:USERPROFILE\orbis_desktop_src\obj-orbis\dist"
$test = "$env:USERPROFILE\orbis_desktop_src\test-install"
Expand-Archive "$dist\orbis-160.0.en-US.win64.zip" -DestinationPath $test
Copy-Item "$env:USERPROFILE\orbis_desktop_src\firefox\orbis-dist\*" "$test\orbis" -Recurse -Force
```

`$test\orbis` then has the layout Firefox expects: `orbis.cfg` next to `orbis.exe`, `autoconfig.js` in
`defaults\pref\` and `policies.json` in `distribution\`. These two commands are reconstructed from the result
(the build engineer's scripts did not record them): the test install's files match the zip and `orbis-dist`.

### Fixes

Option A (used for the MSIX, `scripts/make-msix.ps1`, see `docs/MSIX.md`): `mach repackage msix` accepts a folder
as its input and packs every file in it, whatever the package manifest lists. It also treats the input's
`distribution\` folder as a distribution folder. The script stages the zip plus `orbis-dist` and runs:

```
./mach repackage msix --input <stage>/orbis --arch x86_64 --channel unofficial --version <X.Y.Z.0> \
  --vendor <identity prefix> --identity-name Orbis --publisher <...> --publisher-display-name <...> --output <file>.msix
```

Checked in the second build's MSIX: `orbis.cfg`, `defaults\pref\autoconfig.js` and `distribution\policies.json`
are under `VFS\ProgramFiles\Orbis Browser Package Root\`, byte-identical to `orbis-dist`.

Option B, in the build, so that `mach package` itself includes the files:

1. `apply-overlay.ps1` also copies the three files into the branding folder, and the branding's `moz.build`
   installs them into `dist\bin`: `FINAL_TARGET_FILES[".."]` for `orbis.cfg`,
   `FINAL_TARGET_FILES[".."].defaults.pref` for `autoconfig.js`, `FINAL_TARGET_FILES[".."].distribution` for
   `policies.json` (the branding's `DIST_SUBDIR` is `browser`, so `..` is the install folder; Firefox's own
   `branding-common.mozbuild` installs `firefox.VisualElementsManifest.xml` the same way).
2. A patch to `browser/installer/package-manifest.in` lists them: `@BINPATH@/orbis.cfg`,
   `@RESPATH@/defaults/pref/autoconfig.js`, `@RESPATH@/distribution/policies.json`. Firefox lists
   `@RESPATH@/distribution/*` only `#if defined(BUILT_BY_MOZILLA)`.

Option B makes every package complete, but it needs a patch and a build to check that the packager accepts the
entries. Option A needs no patch for the policy files. Recommendation: A for the MSIX now (done), B later.
Either way, the check in step 5 (prefs locked, policies active, the uBlock Origin consent screen) is what proves
the files are in.

### Mozilla's MSIX `distribution.ini`

`mach repackage msix` always adds `browser/installer/windows/msix/distribution/distribution.ini` (`id=mozilla-MSIX`,
`about=Windows MSIX package`) before any other distribution folder, and skips later files with the same name. The
About dialog shows these two values, so an MSIX would say "mozilla-MSIX - 1.0" there. Fixed by
`patches/0004-msix-no-mozilla-distribution.patch`, which deletes that template file: the Orbis MSIX has no
`distribution.ini` (`docs/MSIX.md`).

## 3b. MSIX

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make-msix.ps1
```

Unsigned `.msix` in `%USERPROFILE%\orbis_desktop_src\msix\`; values and checks in `docs/MSIX.md`. About 30 seconds.

## 5. Check the build

`scripts/verify-build.py` drives the test install through Marionette, using the Marionette client from the Firefox
checkout. Close every Orbis window first. From the Orbis repository:

```
$inst = "$env:USERPROFILE\orbis_desktop_src\test-install\orbis"
$out  = "$env:USERPROFILE\orbis_desktop_src\verify-results"
python -I scripts\verify-build.py default $inst $out          # profile folder; Firefox's profiles untouched
python -I scripts\verify-build.py idle    $inst $out\idle     # 3 minutes idle: DNS log, prefs, policies, no uBO
python -I scripts\verify-build.py hosts   $inst $out\idle     # host names the idle run looked up
python -I scripts\verify-build.py consent $inst $out\accept  accept   # first-run screen, accepted: uBO + 13 lists
python -I scripts\verify-build.py consent $inst $out\decline decline  # first-run screen, declined: no uBO, no AMO
python -I scripts\verify-build.py consent $inst $out\accept-de  accept  --system-locale de-DE   # same, on a
python -I scripts\verify-build.py consent $inst $out\decline-de decline --system-locale de-DE   # German Windows
python -I scripts\verify-build.py consent $inst $out\close   close    # left unanswered: back at next start
python -I scripts\verify-build.py consent $inst $out\close-de close --system-locale de-DE
python -I scripts\verify-build.py consent $inst $out\early   early    # "Start browsing" before Firefox's Add
python -I scripts\verify-build.py consent $inst $out\cancel  cancel   # "Cancel" in Firefox's Add prompt
python -I scripts\verify-build.py consent $inst $out\url     url      # unanswered, then a start with a URL
python -I scripts\verify-build.py second  $inst $out\second <profile folder printed by the consent accept phase>
python -I scripts\verify-build.py ui      $inst $out\ui       # window titles, new tab, About dialog
```

The script's header lists every output file. What to compare:

- `default`: `b-dirs.json` puts the profile under `%APPDATA%\Orbis` and `%LOCALAPPDATA%\Orbis`; in `b-before.json`
  and `b-after.json` the `%APPDATA%\Mozilla\Firefox` `profiles.ini` and `installs.ini` hashes are the same. This
  phase starts Orbis with its real default profile, so it refuses to run unless the install's `application.ini`
  has `Profile=Orbis` and `RemotingName=orbis`. The other phases use new, uniquely named profiles under
  `%USERPROFILE%\orbis_desktop_src\test-profiles`; `second` accepts only a profile inside that folder. Every phase
  stops the Orbis it started, also after an error (Marionette quit, then `taskkill /T /F` on its PID).
- `idle`: in `checks-idle.json` every pref has the value and lock state in `docs/SETTINGS.md`, `policiesStatus`
  equals `STATUS_ACTIVE` and `about:policies` shows no errors. Nobody answers the first-run screen in this phase,
  so `ubo` must be null: no silent install.
- `consent`: every `consent-<choice>.json` ends with `"result": "PASS"`. The `pass` map names each check:
  - all choices: the screen is shown with the box checked, and there is no uBlock Origin, install or
    `addons.mozilla.org` lookup before the answer;
  - accept: uBlock Origin is active with exactly the 13 `3rdparty` lists, and removing it again (in the first
    later start) does not bring the screen back;
  - decline: the warning about phishing and malware protection shows; there is no uBlock Origin and no
    `addons.mozilla.org` lookup at all;
  - close: the screen is left and Orbis quit without an answer, so no choice is recorded;
  - early: "Start browsing" before Firefox's Add prompt; cancel: "Cancel" in that prompt. Both leave no uBlock
    Origin, and the choice is `accepted`;
  - url: like close, then a start with `about:logo` on the command line, which opens that page and keeps
    `browser.shell.disableStartMenuPin` true;
  - close, early, cancel, url: the screen is back at the next plain start, where `browser.shell.disableStartMenuPin`
    is true (no MSIX Start-menu re-pin; it was false on the real first run), and is declined there;
  - all choices: two later starts do not show the screen. Any host ending in
  `addons.mozilla.org` counts. The `--system-locale de-DE` runs set `intl.multilingual.aboutWelcome.systemLocaleOverride`
  in the test profile, so `about:welcome` sees a Windows language that differs from Orbis's; without the
  `languageMismatchEnabled` lock it would then ask `services.addons.mozilla.org` for language packs before the answer.
  `consent-<choice>-screen.png` shows the screen. The accept run also runs the `idle` checks
  (`checks-consent-accept.json`). The test accepts Firefox's "Add uBlock Origin?" prompt itself; it runs headless,
  so look at the screen once in a real window too.
- `second`: on the accepted profile, `selectedFilterLists` still matches the `3rdparty` policy.
- `hosts`: every host is in `docs/SETTINGS.md`, "Network calls that remain". A new host must be added there with a
  reason, or blocked, before release. The idle phase logs with `MOZ_LOG=timestamp,sync,nsHostResolver:5`: without
  `sync`, the first build's DNS log lost everything after the first 30 seconds when the release build shut down.
- `ui`: window titles say "Orbis"; `g-main-window.png` shows no Firefox logo and no default top sites;
  `g-about.png`, `aboutVisibleText` and `aboutLinks` in `g-ui.json` pass the About dialog test in
  `docs/PATCHES.md` (judge by `aboutVisibleText`, not `aboutText`, which includes hidden elements).

Not covered yet: the MSIX package running (it is built and its contents checked, but not installed:
`docs/MSIX.md`, "Local install test"), the Firefox-installed profile test from `docs/PATCHES.md` on a separate PC,
and the version resources of the binaries (`(Get-Item orbis.exe).VersionInfo`).
