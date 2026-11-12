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

Output: `%USERPROFILE%\orbis_desktop_src\msix\<identityName>_<version>_x64.msix`, **unsigned**. `msix-work\`
keeps the stage, the unpacked package, `AppxManifest.xml` and `repackage-msix.log`. `-CheckOnly` re-checks an
existing package without rebuilding it. `makeappx.exe` comes from the Windows SDK that `mach bootstrap` installed
(`%USERPROFILE%\.mozbuild\vs\Windows Kits\10\bin\<version>\x64`).

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
| `capabilities` | `["runFullTrust"]` | checked only | Firefox's template declares exactly one capability, `rescap:runFullTrust` (a Win32 desktop app in a package needs it). The script fails if the manifest has any other list. The Store asks for a justification of restricted capabilities at submission: "Orbis is a desktop web browser (Win32) packaged with the Desktop Bridge" |
| `assets` | `overlay/browser/branding/orbis/msix/Assets` | `Assets\` | Placeholder art (`docs/BRANDING.md`). mach copies `<branding>/msix/Assets` from the build's `--with-branding` folder; the script checks that every file in the package is byte-identical to this folder. The file names match Firefox's official branding, which the template's `Resources.pri` expects |

When Shibi has reserved the name: copy the three Partner Center values into `identityName`, `publisher` and
`publisherDisplayName`, rebuild with `make-msix.ps1`, and upload. Nothing secret goes into the file: these three
values are public (they are in every installed package's manifest).

### Version

`Package/Identity/Version` is four numbers, each at most 65535, and the Store requires the last to be 0. mach's
default (`get_embedded_version`) maps Firefox `X.Y` to `X.Y.0.0` and `X.Y.Z` to `X.Y.Z.0`, which leaves no room
for an Orbis-only rebuild of the same Firefox (a settings fix, new artwork): the Store refuses a package whose
version is not higher than the published one.

`make-msix.ps1` passes `--version X.Y.(Z*100+R).0`, with `X.Y.Z` from `application.ini` and `R` =
`orbisRevision` (0 to 99):

| Firefox | `orbisRevision` | MSIX version |
|---|---|---|
| 160.0 | 0 | 160.0.0.0 |
| 160.0 | 1 | 160.0.1.0 |
| 160.0.1 | 0 | 160.0.100.0 |
| 160.0.2 | 3 | 160.0.203.0 |
| 161.0 | 0 | 161.0.0.0 |

Reset `orbisRevision` to 0 with every Firefox version bump; raise it for each Orbis-only rebuild. Versions always
increase. The browser's own version (About dialog, user agent) stays the Firefox version.

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

`scripts/apply-patches.ps1` now accepts a patch that deletes a file when it checks whether the series is
already applied. Undo: the `git checkout` line in `docs/PATCHES.md` (it now names the `.ini`).

## What the script checks in the package

After `makeappx unpack`:

- `AppxManifest.xml`: `Identity` `Name`, `Publisher`, `Version`, `ProcessorArchitecture` x64,
  `Properties/DisplayName`, `PublisherDisplayName`, the tile `DisplayName`, the capability list, and
  `Application/@Executable` `VFS\ProgramFiles\Orbis Package Root\orbis.exe`. Outside comments it must not contain
  "Mozilla" or "Firefox", except `Mozilla.MsixComServer.BackgroundTaskHost` (open items).
- `Assets\`: every placeholder file, byte-identical.
- `VFS\ProgramFiles\Orbis Package Root\`: `orbis.cfg`, `defaults\pref\autoconfig.js` and
  `distribution\policies.json`, byte-identical to `orbis-dist`; the `distribution` folder has only
  `policies.json`; no `distribution.ini` anywhere in the package; no file with `mozilla-MSIX`.

## Local install test (not done: needs Shibi's choice)

Nothing here has been run. Each option changes Shibi's PC, so each needs Shibi's explicit OK (`AGENTS.md`).
Profile note: the installed Orbis uses `%APPDATA%\Orbis` (or its MSIX-virtualised copy under
`%LOCALAPPDATA%\Packages\<package family>\LocalCache`). The profile-isolation test in `docs/PATCHES.md` still
belongs on a PC with Firefox installed, not this one.

1. **Wait for the Store (no change to the PC now).** Shibi reserves the name, the three TODO-STORE values are
   filled in, the unsigned `.msix` is uploaded, and Partner Center signs it. Install the first build from a
   private audience or a hidden listing. Slowest, but tests exactly what users get.
2. **Self-signed test certificate.** Needs a test `publisher` value (for example `CN=Orbis Test`) and a rebuild,
   then: create a code-signing certificate with that subject (`New-SelfSignedCertificate`, in
   `Cert:\CurrentUser\My`), sign with `signtool sign /fd SHA256` (in the same Windows SDK folder as `makeappx`),
   and trust the certificate. Microsoft's sideloading documentation installs it into **Local Machine** "Trusted
   People" (an administrator prompt); a certificate only in the current user's store is not enough for the
   package installer (from Microsoft's documentation, not tested here). Then double-click the `.msix` or
   `Add-AppxPackage <file>.msix`. Developer Mode is **not** needed for a signed package (sideloading is on by
   default since Windows 10 2004). Undo: remove the app, then delete the certificate from both stores. A test
   certificate in the machine's trusted store is a real security change: anything signed with its key would be
   trusted, so the key must be deleted after the test.
3. **Developer Mode and the unpacked folder, no certificate.** Turn on Developer Mode (Settings > System > For
   developers), then `Add-AppxPackage -Register <msix-work>\unpacked\pkg\AppxManifest.xml`. Tests the manifest and
   the file layout, not the `.msix` file itself. Undo: remove the app, turn Developer Mode off.
4. **Unsigned package with Microsoft's unsigned OID (Windows 11).** `make-msix.ps1 -AllowUnsignedInstall` builds
   `..._unsigned-test.msix`, whose publisher ends in `OID.2.25.311729368913984317654407730594956997722=1` (mach's
   `--unsigned`); an elevated PowerShell runs `Add-AppxPackage -Path <file> -AllowUnsigned`. No certificate and no
   Developer Mode, but an administrator prompt. Never upload this variant. (Built and checked; not installed.)

Recommendation: 3 or 4 for a first look (no certificate to clean up), then 1 for the real test.

## Open items

- **`Mozilla.MsixComServer.BackgroundTaskHost`.** The manifest's background-task and in-process-server class ID
  is `MOZ_BACKGROUNDTASK_ACTIVATABLE_CLASS_ID` from the build (`AppConstants`), not set by the branding. It is an
  internal identifier (not shown to users; `docs/BRANDING.md` rule 5), registered per package. Whether it clashes
  with an installed Firefox MSIX on the same PC is not tested.
- **Manifest content from Firefox's template, unchanged:** file-type and `http`/`https`/`mailto` associations,
  the notification COM server (`notificationserver.dll`), the disabled `LaunchOnLogin` startup task, the
  accessibility proxy, `TargetDeviceFamily` MinVersion 10.0.17763.0, tile background `#20123A`. Review with the
  real artwork (PR 9).
- **Store checks not run:** Windows App Certification Kit and Partner Center's package validation.
- **`mach package` still leaves out `orbis-dist`** (option B in `docs/BUILD.md`); this script works around it.
- **Store identity names that do not end in `.Orbis`** would need `repackage_msix()` called with its `identity`
  argument, which `mach repackage msix` does not expose.
