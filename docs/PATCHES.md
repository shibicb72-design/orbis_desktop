# Orbis Desktop source patches

Changes to Mozilla's own files. The Firefox source is never edited by hand: every change is a file in `patches/`,
applied by `scripts/apply-patches.ps1`. A patch is the last resort. Each one below says why no build option, policy
or pref can do the same.

## How to apply

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-patches.ps1 -Check   # checks only, writes nothing
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-patches.ps1          # applies
```

The script applies `patches\*.patch` in name order as one series with `git apply` (all or nothing). It refuses, and
writes nothing, when the checkout is not on `C:`, is inside this repository, passes through a junction, is not a
Firefox git checkout, is not at the commit pinned in `upstream/firefox.json`, has changes to tracked files, or when
`git apply --check` fails. Untracked files (the overlay's `browser\branding\orbis`, `mozconfig`, `orbis-dist`) are
allowed. If exactly these patches are already applied, it says so and exits 0.

Undo: `git -C <checkout> checkout -- browser/moz.configure browser/app/module.ver browser/app/pbproxy/module.ver
ipc/app/module.ver`.

When the Firefox pin moves (`docs/UPDATING.md`), run `apply-patches.ps1 -Check` on the new checkout. A patch that
no longer applies is rebased by hand and its index lines regenerated; never applied with `--reject` or fuzz.

Order: `fetch-firefox.ps1`, then `apply-patches.ps1`, then `apply-overlay.ps1` (PR #3), then `mach build`.

## The patches

| Patch | Files | What | Why no setting can do it |
|---|---|---|---|
| `0001-profile-folder-orbis.patch` | `browser/moz.configure` | Adds `imply_option("MOZ_APP_PROFILE", "Orbis")` | `MOZ_APP_PROFILE` is a `project_flag` (`toolkit/moz.configure`): it takes only "implied" values from a project's `moz.configure`, not a mozconfig option or environment variable |
| `0002-version-resource-orbis.patch` | `browser/app/module.ver`, `browser/app/pbproxy/module.ver`, `ipc/app/module.ver` | `WIN32_MODULE_COMPANYNAME` `Mozilla Corporation` becomes `Orbis`; `WIN32_MODULE_TRADEMARKS` `Firefox is a Trademark of The Mozilla Foundation.` becomes empty (added, empty, to `ipc/app/module.ver`) | These files are read as they are by `config/create_rc.py`; no build option sets them |

### 0001: profile folder

Without it, Orbis and an installed Firefox share their profiles. On Windows the profile folder is
`%APPDATA%\<vendor>\<basename>` (`nsXREDirProvider::AppendFromAppData`), and Firefox 160's `browser/moz.configure`
implies vendor `Mozilla`; Orbis keeps basename `Firefox` (below). So both would use `%APPDATA%\Mozilla\Firefox` and
`%LOCALAPPDATA%\Mozilla\Firefox`: one `profiles.ini`, one `installs.ini`. Firefox's dedicated-profile logic
(`MOZ_DEDICATED_PROFILES`) gives each install its own default profile by install path hash, but both programs still
read and write the same `profiles.ini` and `installs.ini`, and either can open the other's profiles from the
profile manager. Packaging as MSIX is not a fix: Firefox's code expects to share these files when packaged (for a
package, `nsXREDirProvider::GetInstallHash` hashes the package family name to pick a dedicated profile entry in
the same `installs.ini`, and `MaybeMakeDefaultDedicatedProfile` runs as usual). Whether MSIX file-system
virtualisation would redirect some writes was not tested; the test plan below must pass either way.

With `MOZ_APP_PROFILE` set, `build/application.ini.in` writes `Profile=Orbis` into `application.ini`, and
`AppendFromAppData` uses `%APPDATA%\Orbis` and `%LOCALAPPDATA%\Orbis` instead (the profile name replaces both vendor
and basename).

Why not the other ways:

- **`--with-app-basename=Orbis`** (or vendor): the basename is `Services.appinfo.name`. `nsHttpHandler.cpp` adds
  the `Firefox/160.0` user-agent token only when the app name is `Firefox`, so the user agent would end in
  `Orbis/160.0`, which marks every Orbis user and breaks sites that check for Firefox. `SearchEngineSelector`
  passes `Services.appinfo.name` to the search configuration, so the built-in engine list would change. The
  basename must stay `Firefox`.
- **`MOZ_APP_VENDOR`**: also a `project_flag`, so it needs a patch too, and the vendor appears in more places
  (registry paths, `application.ini` `Vendor`). The profile name is the narrowest change.

### 0002: executable version resource

`config/create_rc.py` builds each executable's version resource (File Properties > Details) from the `module.ver`
next to it. Firefox 160's files say `CompanyName` "Mozilla Corporation" and `LegalTrademarks` "Firefox is a
Trademark of The Mozilla Foundation." on `orbis.exe` and `private_browsing.exe`, and `CompanyName` "Mozilla
Corporation" with the default `LegalTrademarks` "Mozilla" on `plugin-container.exe`. Orbis is not made by Mozilla,
so this is a Store blocker.

- The `WIN32_MODULE_TRADEMARKS` key stays, with an empty value: if the key is missing, `create_rc.py` writes its
  default, "Mozilla". `ipc/app/module.ver` had no such key, so the patch adds it, empty.
- `FileDescription` and `ProductName` are `@MOZ_APP_DISPLAYNAME@`, which is "Orbis" from the branding's
  `configure.sh`, so they are not patched.
- `LegalCopyright` ("©Firefox and Mozilla Developers; available under the MPL 2 license.") is left alone: it is
  a true statement about who holds copyright in the code, not a product name.
- `ipc/app/module.ver` has CRLF line endings in Mozilla's repository; the patch keeps them, and
  `.gitattributes` marks `patches/**` as `-text` so Git never rewrites the patch bytes. The `©` in the context
  lines is the single byte `0xA9`, as in Mozilla's files.

Not covered by this patch (open items):

- Every other executable and DLL without a `module.ver` (`xul.dll`, `mozglue.dll`, `nss3.dll` and others) gets
  `create_rc.py`'s defaults: `CompanyName` "Mozilla Foundation" and `LegalTrademarks` "Mozilla". Fixing that means
  patching `create_rc.py`'s defaults; to decide before the Store submission.
- `create_rc.py` writes `Identity LimitedAccessFeature { L"MozillaFirefox_pcsmm0jrprpb2" }`: Mozilla's identity
  for a Windows Limited Access Feature (taskbar pinning). Orbis must not claim it; to check what fails without it.

## Test plan (needs a build; not run yet)

Profile isolation, on a test PC or VM with Firefox installed and used at least once, **not on Shibi's PC** while
the profile collision is unfixed (`docs/BRANDING.md`):

1. Close Firefox. Record SHA-256 hashes of `%APPDATA%\Mozilla\Firefox\profiles.ini` and
   `%APPDATA%\Mozilla\Firefox\installs.ini`, and the file list with sizes and dates of `%APPDATA%\Mozilla\Firefox`
   and `%LOCALAPPDATA%\Mozilla\Firefox`.
2. Install the Orbis MSIX, start it, browse, let uBlock Origin install, close it. Start it a second time and close.
3. Pass: both `.ini` files are byte-identical (same hashes), nothing in the two Mozilla folders was added or
   changed, and Orbis's profile is under `%APPDATA%\Orbis` and `%LOCALAPPDATA%\Orbis` (or their MSIX-virtualised
   equivalents under `%LOCALAPPDATA%\Packages\<package>\LocalCache`).
4. Start Firefox: it opens its own profile with no "profile missing" or "older version" prompt.
5. With Firefox running, start Orbis: it opens its own window, not a new Firefox window, and vice versa.

Version resource: on the built `orbis.exe`, `private_browsing.exe` and `plugin-container.exe`, File Properties >
Details (or `(Get-Item orbis.exe).VersionInfo`) shows `CompanyName` Orbis, empty `LegalTrademarks`, and no
"Mozilla Corporation".

## Still shared with Firefox

- **Enterprise-policy registry keys.** `EnterprisePoliciesParent` reads `SOFTWARE\Policies` under HKCU, then HKLM,
  and `WindowsGPOParser` opens `Mozilla\` + `Services.appinfo.name`. With the basename `Firefox`, Orbis reads
  **`HKLM\SOFTWARE\Policies\Mozilla\Firefox`** (and the same path under HKCU): any Firefox group policy set by an
  administrator also applies to Orbis, merged with Orbis's `distribution\policies.json`. Not fixed: changing it
  needs the basename (see above) or a patch to `WindowsGPOParser`. Document it; it only matters on managed PCs.
- **Native messaging, managed storage and PKCS #11 registry keys.** `NativeManifests.sys.mjs` looks up
  **`Software\Mozilla\NativeMessagingHosts`** (and `ManagedStorage`, `PKCS11Modules`) under HKCU, then HKLM. The path
  is fixed in the code, not built from the vendor or basename, so any native-messaging host registered for Firefox
  (password managers, for example) is also offered to Orbis's extensions. Not fixed: only a patch could change it.
- **Registry-installed add-ons.** `XPIProvider.sys.mjs` (`WinRegLocation`) reads
  **`SOFTWARE\Mozilla\Firefox\Extensions`** (`SOFTWARE\<vendor>\<basename>\Extensions`; Orbis keeps vendor `Mozilla`
  and basename `Firefox`) under HKCU and HKLM. An add-on registered there for Firefox is seen by Orbis too; Firefox's
  default `extensions.autoDisableScopes` (15) installs such add-ons disabled until the user enables them. Not fixed:
  changing it needs the vendor or basename, or a patch.
