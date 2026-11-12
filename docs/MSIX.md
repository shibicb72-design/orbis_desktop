# Orbis Desktop MSIX package

How the Orbis MSIX is made from the build, what goes into it, which values wait for the Microsoft Store account,
and what a local install test would need. Option A of `docs/BUILD.md`: `mach repackage msix` on the unpacked
application folder with `orbis-dist` added. No Mozilla file is edited by hand; the only patch is 0004.

## Make it

After `mach build` and `mach package` (`docs/BUILD.md`, steps 1 to 3), with patches 0001 to 0004 applied:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make-msix.ps1
```

The script:

1. Refuses unless every path is on drive C:, outside this repository and not through a junction, and the
   checkout has patch 0004 applied (the MSIX template's `distribution.ini` is gone).
2. Stages `msix-work\stage\orbis\`: the build's `orbis-<version>.en-US.win64.zip` expanded, plus `orbis-dist\`
   (`orbis.cfg`, `defaults\pref\autoconfig.js`, `distribution\policies.json`). Same layout as the test install
   in `docs/BUILD.md`.
3. Runs `./mach repackage msix` in MozillaBuild's shell with the values from `packaging/msix-config.json`.
4. Unpacks the `.msix` with `makeappx unpack` and checks it (below). Exit code 0 only if every check passes.
5. Prints the package's SHA-256 and writes it to `<package>.msix.sha256` next to the package.

Output: `%USERPROFILE%\orbis_desktop_src\msix\<identityName>_<version>_x64.msix`, **unsigned**. `msix-work\`
keeps the stage, the unpacked package, `AppxManifest.xml` and `repackage-msix.log`. With `-AllowUnsignedInstall`
the default work folder is `msix-work-unsigned-test\` instead, so a test build never overwrites the Store
build's folder. mach also writes its own temporary copy of the package to
`%USERPROFILE%\.mozbuild\cache\mach-msix\msix-temp-<channel>\` and replaces it on every run. `-CheckOnly`
re-checks an existing package without rebuilding it. `makeappx.exe` comes from the Windows SDK that
`mach bootstrap` installed (`%USERPROFILE%\.mozbuild\vs\Windows Kits\10\bin\<version>\x64`).

**Store identity placeholders.** While `packaging/msix-config.json` still has `TODO-STORE` values, the script
prints a warning block at the start and a warning at the end: such a package cannot be uploaded. Build every
package meant for upload with `-RequireStoreIdentity`, which refuses (exit 1) while any placeholder is left:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make-msix.ps1 -RequireStoreIdentity
```

## Settings: `packaging/msix-config.json`

| Key | Value now | Goes to | Notes |
|---|---|---|---|
| `identityName` | `TODO-STORE.Orbis` | `Package/Identity/Name` | **TODO-STORE.** Partner Center assigns it when Shibi reserves the name (Product identity page, "Package/Identity/Name", often `<digits><publisher>.<name>`). mach builds it as `<--vendor>.<--identity-name>`, so it must end in `.` + `displayName` without spaces; the script splits it and refuses any other form |
| `publisher` | `CN=TODO-STORE` | `Package/Identity/Publisher` | **TODO-STORE.** Partner Center's "Package/Identity/Publisher" (`CN=<GUID>`). The Store signs the package with it. A local signed test needs a certificate whose subject is exactly this value |
| `publisherDisplayName` | `TODO-STORE` | `Package/Properties/PublisherDisplayName` | **TODO-STORE.** Partner Center's "Package/Properties/PublisherDisplayName" (the account's publisher name). mach's default would be "Mozilla Corporation" |
| `displayName` | `Orbis` | `--identity-name`: tile and Start menu name (`uap:VisualElements/@DisplayName`), install folder `VFS\ProgramFiles\Orbis Package Root\`, identity suffix | Must equal the name reserved in Partner Center. `Package/Properties/DisplayName` itself is not set from here: mach takes it from `brandFullName` in the branding's `brand.properties` ("Orbis"). The script checks that both say this value |
| `channel` | `unofficial` | mach `--channel` | Orbis is not a Mozilla channel. In `msix.py` the channel only adds " Beta" or " ESR" to names (not for `unofficial`) and names mach's temporary folder |
| `arch` | `x86_64` | `ProcessorArchitecture` `x64` | The only architecture Orbis builds |
| `orbisRevision` | `0` | `Package/Identity/Version` | See "Version" |
| `capabilities` | `["runFullTrust"]` | checked only | Firefox's template declares exactly one capability, `rescap:runFullTrust` (a Win32 desktop app in a package needs it). The script fails if the manifest has any other list. The Store asks for a justification of restricted capabilities at submission: the text is in `docs/STORE-SUBMISSION.md` |
| `assets` | `overlay/browser/branding/orbis/msix/Assets` | `Assets\` | Placeholder art (`docs/BRANDING.md`). mach copies `<branding>/msix/Assets` from the build's `--with-branding` folder; the script checks that every file in the package is byte-identical to this folder. The file names match Firefox's official branding, which the template's `Resources.pri` expects |

When Shibi has reserved the name: copy the three Partner Center values into `identityName`, `publisher` and
`publisherDisplayName`, rebuild with `make-msix.ps1 -RequireStoreIdentity`, and upload. Nothing secret goes into the file: these three
values are public (they are in every installed package's manifest).

### Version

`Package/Identity/Version` is four numbers, each at most 65535, and the Store requires the last to be 0. mach's
default (`get_embedded_version`) maps Firefox `X.Y` to `X.Y.0.0` and `X.Y.Z` to `X.Y.Z.0`, which leaves no room
for an Orbis-only rebuild of the same Firefox (a settings fix, new artwork). The Store does not refuse a lower
version (packages can be submitted in any order), but a device always takes the highest version it can get, so
a rebuild that does not raise the version never replaces what users already have.

`make-msix.ps1` passes `--version X.Y.(Z*100+R).0`, with `X.Y.Z` from `application.ini` and `R` =
`orbisRevision` (0 to 99):

| Firefox | `orbisRevision` | MSIX version |
|---|---|---|
| 160.0 | 0 | 160.0.0.0 |
| 160.0 | 1 | 160.0.1.0 |
| 160.0.1 | 0 | 160.0.100.0 |
| 160.0.2 | 3 | 160.0.203.0 |
| 161.0 | 0 | 161.0.0.0 |

Reset `orbisRevision` to 0 with every Firefox version bump; raise it for each Orbis-only rebuild. Keep versions
always increasing; the Store does not enforce it. The browser's own version (About dialog, user agent) stays the Firefox version.

## Mozilla's `distribution.ini`: patch 0004

`msix.py` always adds `browser/installer/windows/msix/distribution/` before any other distribution folder,
including the input's own `distribution\`, and skips later files with the same name. That folder holds Mozilla's
`distribution.ini` (`id=mozilla-MSIX`, `about=Windows MSIX package`, "Author: Mozilla"), which the About dialog
would show and which sets `distribution.id` to `mozilla-MSIX`. mach has no option to leave it out: the template
path comes from the checkout and `--distribution-dir` folders are added after it.

Options read in the pinned source:

- **Patch 0004 deletes the template file (chosen).** `FileFinder` returns nothing for the missing folder (seen
  in the build: "Adding distribution files from .../msix/distribution", then only `policies.json`). No build step
  reads the file (`git grep`: only `msix.py`'s folder and a UITour test). Result: Orbis ships no
  `distribution.ini`, the same as the test install and the zip that `verify-build.py` checked.
- A patch that rewrites it with Orbis values: Orbis has no partner distribution, and an `id` would set
  `distribution.id`, which Firefox passes on to the search configuration. Nothing to gain.
- An Orbis `distribution.ini` in `orbis-dist\distribution\`: skipped by mach as a duplicate. Does not work.
- Calling `repackage_msix()` from our own Python with a copied template: more code, and a second copy of
  Mozilla's template to keep current.

Side effect: the deleted file's `[Preferences]` also set `intl.locale.requested` to `""` and
`intl.multilingual.enabled` to `true` (follow the Windows display language, and allow language packs). Orbis
drops both. That is harmless while Orbis is English only: there is no other locale to pick, and
`ExtensionSettings` blocks language packs. If Orbis ever ships more locales, set the two prefs in `orbis.cfg`.

`scripts/apply-patches.ps1` now accepts a patch that deletes a file when it checks whether the series is
already applied. Undo: the `git checkout` line in `docs/PATCHES.md` (it now names the `.ini`).

## What the script checks in the package

After `makeappx unpack`:

- `AppxManifest.xml`: `Identity` `Name`, `Publisher`, `Version`, `ProcessorArchitecture` x64,
  `Properties/DisplayName`, `PublisherDisplayName`, the tile `DisplayName`, the capability list, and
  `Application/@Executable` `VFS\ProgramFiles\Orbis Package Root\orbis.exe`. Outside comments it must not contain
  "Mozilla" or "Firefox", except `Mozilla.MsixComServer.BackgroundTaskHost` (open items).
- `Assets\`: every placeholder file, byte-identical, and two-way: a file in the package's `Assets\` that is not
  in the config's folder also fails.
- `VFS\ProgramFiles\Orbis Package Root\`: `orbis.cfg`, `defaults\pref\autoconfig.js` and
  `distribution\policies.json`, byte-identical to `orbis-dist`; the `distribution` folder has only
  `policies.json`; no `distribution.ini` anywhere in the package; no file with `mozilla-MSIX`.

Reported, never a failure (they are known open items in `docs/BRANDING.md`):

- File names in the package that contain "Mozilla" or "Firefox". Build of 2026-11-12: 2
  (`firefox.VisualElementsManifest.xml`, `fonts\TwemojiMozilla.ttf`).
- `.exe` and `.dll` files whose version resource (`CompanyName`, `ProductName`, `FileDescription`,
  `LegalCopyright`, `LegalTrademarks`, `InternalName`, `OriginalFilename`, `Comments`) contains "Mozilla" or
  "Firefox". Build of 2026-11-12: 23, of which 21 say `CompanyName` "Mozilla Foundation" and `LegalTrademarks`
  "Mozilla", and 2 (`orbis.exe`, `private_browsing.exe`) only `LegalCopyright` "(c)Firefox and Mozilla Developers;
  available under the MPL 2 license." (kept on purpose, `docs/PATCHES.md`, patch 0002).

## Local install test (not done: needs Shibi's choice)

Nothing here has been run. Each option changes Shibi's PC, so each needs Shibi's explicit OK (`AGENTS.md`).
Profile note: the installed Orbis uses `%APPDATA%\Orbis` (or its MSIX-virtualised copy under
`%LOCALAPPDATA%\Packages\<package family>\LocalCache`). The profile-isolation test in `docs/PATCHES.md` still
belongs on a PC with Firefox installed, not this one.

**Recommendation: option 4 first, then option 1. Do not use option 2. Option 3 is not recommended.**

- Option 4 tests the real `.msix` file with one elevated command and leaves nothing to clean up but the app.
- Option 1 then tests exactly what users get, signed by the Store.
- Option 2 is not worth its risk (see its reasons below).
- Option 3 registers a folder that the next `make-msix.ps1` run deletes, and runs a full-trust app from a
  folder any program of the user can write to.

1. **Store private audience (no change to the PC now; second step).** Shibi reserves the name, the three
   TODO-STORE values are filled in, the package is built with `-RequireStoreIdentity`, the unsigned `.msix` is
   uploaded, and Partner Center signs it. Install it from a private audience (or a hidden listing). Slowest, but
   tests exactly what users get.
2. **Self-signed test certificate. Do not use.** Reasons:
   - The certificate must be trusted in the **Local Machine** "Trusted People" store: a machine-wide security
     change. Until it is removed, anything signed with its key is trusted, and the private key sits on this PC.
   - It needs a different `publisher` and a rebuild, so it tests a package that is not the one uploaded.
   - It has the most steps and the most to undo (two certificate stores, the key), and a missed step leaves the
     trust in place.

   Steps, for the record only: set a test `publisher` value (for example `CN=Orbis Test`) and rebuild,
   then create a code-signing certificate with that subject (`New-SelfSignedCertificate`, in
   `Cert:\CurrentUser\My`), sign with `signtool sign /fd SHA256` (in the same Windows SDK folder as `makeappx`),
   and trust the certificate. Microsoft's sideloading documentation installs it into **Local Machine** "Trusted
   People" (an administrator prompt); a certificate only in the current user's store is not enough for the
   package installer (from Microsoft's documentation, not tested here). Then double-click the `.msix` or
   `Add-AppxPackage <file>.msix`. Developer Mode is **not** needed for a signed package (sideloading is on by
   default since Windows 10 2004). Undo: remove the app, then delete the certificate and its key from both
   stores.
3. **Developer Mode and the unpacked folder, no certificate. Not recommended.** Turn on Developer Mode
   (Settings > System > For developers), then `Add-AppxPackage -Register <msix-work>\unpacked\pkg\AppxManifest.xml`.
   Tests the manifest and the file layout, not the `.msix` file itself. Undo: remove the app, turn Developer Mode
   off. **Warnings:**
   - The registered app runs from `msix-work\unpacked\pkg`, and `make-msix.ps1` deletes and recreates that folder
     on its next run (also with `-CheckOnly`). The installed app then breaks, or silently runs whatever the next
     run unpacked.
   - It runs a full-trust app (`runFullTrust`) from a user-writable folder: any program running as the user can
     change its files, and no signature protects files registered from a folder. A Store install
     lives in the protected `WindowsApps` folder instead.
4. **Unsigned package with Microsoft's unsigned OID (Windows 11). Recommended first step.**
   `make-msix.ps1 -AllowUnsignedInstall` (not elevated) builds `..._unsigned-test.msix` in its own work folder
   (`msix-work-unsigned-test\`), whose publisher ends in `OID.2.25.311729368913984317654407730594956997722=1`
   (mach's `--unsigned`). It prints the package's SHA-256 and writes it to `..._unsigned-test.msix.sha256`. Then
   open an elevated PowerShell and run **only this one command**, with the path and the hash from that file. It
   compares the SHA-256 immediately before installing, so a file changed since the build is not installed:

   ```
   $f = '<full path>\TODO-STORE.Orbis_160.0.0.0_x64_unsigned-test.msix'; if ((Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash -eq '<SHA-256 from the .sha256 file>') { Add-AppxPackage -Path $f -AllowUnsigned } else { 'SHA-256 mismatch: not installed' }
   ```

   Close the elevated window right after. No certificate and no Developer Mode. Undo (not elevated):
   `Get-AppxPackage -Name 'TODO-STORE.Orbis' | Remove-AppxPackage`. Never upload this variant.
   Built and checked on 2026-11-12, not installed: 142,176,013 bytes, SHA-256
   `7585F49524A29E1E5F07F81FC94345D3C8B5BA142AB29A420422B93741F1691C`. The build is not byte-for-byte
   reproducible (the first build of PR #6 had a different hash), so always compare against the `.sha256` of the
   file you install, not against this value.

## Open items

- **`Mozilla.MsixComServer.BackgroundTaskHost`.** The manifest's background-task and in-process-server class ID
  is `MOZ_BACKGROUNDTASK_ACTIVATABLE_CLASS_ID` from the build (`AppConstants`), not set by the branding. It is an
  internal identifier (not shown to users; `docs/BRANDING.md` rule 5), registered per package. Whether it clashes
  with an installed Firefox MSIX on the same PC is not tested.
- **Manifest content from Firefox's template, unchanged:** file-type and `http`/`https`/`mailto` associations,
  the notification COM server (`notificationserver.dll`), the disabled `LaunchOnLogin` startup task, the
  accessibility proxy, `TargetDeviceFamily` MinVersion 10.0.17763.0, tile background `#20123A` (Firefox purple;
  `docs/BRANDING.md`). Review with the real artwork (PR 9).
- **Store checks not run:** Windows App Certification Kit and Partner Center's package validation. Submission
  text, blockers and risks: `docs/STORE-SUBMISSION.md`.
- **`mach package` still leaves out `orbis-dist`** (option B in `docs/BUILD.md`); this script works around it.
- **Store identity names that do not end in `.Orbis`** would need `repackage_msix()` called with its `identity`
  argument, which `mach repackage msix` does not expose.
