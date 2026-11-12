# Orbis Desktop branding

How Orbis names itself, what it may and may not say about Firefox, and where the branding files are.

## Trademark rules

Firefox's source code is MPL-2.0, but the names and logos are not licensed with it. The top-level `LICENSE` file of
the Firefox source says: "You are not granted rights or licenses to the trademarks of the Mozilla Foundation or any
party, including without limitation the Firefox name or logo."

Rules for Orbis (also in `AGENTS.md`):

1. **The product name never contains "Firefox" or "Mozilla".** The name is "Orbis" everywhere a user sees a
   product name: window titles, menus, the About dialog, the Start menu, the Microsoft Store listing, the
   installer, the executable (`orbis.exe`).
2. **No Firefox or Mozilla logos or artwork.** That includes the globe and wordmarks in Firefox's
   `browser/branding/unofficial` template (see "Artwork" below).
3. **Truthful attribution is allowed and wanted:** "Orbis is based on Mozilla's Firefox source code and is not made
   or endorsed by Mozilla. Firefox and Mozilla are trademarks of the Mozilla Foundation." This text is
   `trademarkInfo` in `brand.ftl`, shown in the About dialog.
4. **The user agent keeps "Firefox".** The user agent string is a compatibility signal for websites, not a product
   name. Orbis sends the same string as Firefox 160 on Windows:
   `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:160.0) Gecko/20100101 Firefox/160.0` (observed in the first
   Orbis build: `ua` in `checks-idle.json` from `scripts/verify-build.py idle`).
   In `netwerk/protocol/http/nsHttpHandler.cpp` the `Firefox/160.0` token is added when the application name
   (`MOZ_APP_BASENAME`) is "Firefox". If Orbis changed that name, the string would end in `Orbis/160.0` instead,
   which would make every Orbis user stand out to trackers and break sites that check for Firefox. So
   `MOZ_APP_BASENAME` stays "Firefox".
5. **Internal names may keep "firefox"** where the Firefox build fixes them and users do not see them as a product
   name: `firefox.ico`, `firefox64.ico`, `pref/firefox-branding.js`, `content/firefox-wordmark.svg` (its content is
   the Orbis wordmark), `FirefoxBranding()` in `moz.build`, `MOZ_APP_BASENAME`.

## How the build picks up Orbis branding

| Where | Setting | Value |
|---|---|---|
| `mozconfig` | `--with-branding` | `browser/branding/orbis` |
| `mozconfig` | `--disable-official-branding` | Mozilla's official branding (which would override `--with-branding`) is off |
| `mozconfig` | `--with-app-name` | `orbis`: `orbis.exe`, and the remoting name, so starting Orbis never hands a URL to a running Firefox |
| `configure.sh` | `MOZ_APP_DISPLAYNAME` | `Orbis` |
| `locales/en-US/brand.ftl` | `-brand-short-name`, `-brand-full-name`, `-brand-product-name`, `-vendor-short-name`, ... | `Orbis` |
| `locales/en-US/brand.properties` | `brandShortName`, `brandFullName`, ... | `Orbis` |
| `branding.nsi` | `BrandFullName`, `CompanyName`, URLs, `CertNameDownload` | `Orbis`, the Orbis repository, blank (no NSIS installer is shipped) |
| `pref/firefox-branding.js` | start and welcome pages | empty; the template's updater prefs and `devtools.selfxss.count` are dropped |

`scripts/apply-overlay.ps1` copies `overlay/browser/branding/orbis/` to `browser/branding/orbis/` in the Firefox
checkout and `mozconfig` to the top of the checkout. `scripts/check-mozconfig.py` checks every mozconfig option
against the pinned source.

## Artwork

Every image is a **placeholder marked TODO**: a blue disc with a white "O" and the word "TODO" where it fits
(`overlay/browser/branding/orbis/TODO-PLACEHOLDER-ART.txt`). `scripts/make-placeholder-branding.ps1` draws the PNG,
ICO, BMP and JPG files; the four SVG files were written by hand. Only the file names and pixel sizes come from
Firefox 160's `browser/branding/unofficial`.

Why the template's art was not reused: its images carry no licence notice of their own, `about-logo.svg` (the
blue globe) has no MPL header, `firefox-wordmark.svg` and `about-wordmark.svg` draw the word "Firefox", and the
source's `LICENSE` grants no rights to the Firefox name or logo. Nothing found says the template art is free to
reuse, so none of it is used. Mac-only files (`Assets.car`, `*.icns`, `dsstore`) are left out.

## Open items

- **BUILD BLOCKER: profile collision. Nothing built from this branch may be packaged, installed or run on this PC
  until it is fixed.** `browser/moz.configure` hard-codes `imply_option("MOZ_APP_VENDOR", "Mozilla")`, and
  `MOZ_APP_VENDOR`, `MOZ_APP_PROFILE` and `MOZ_APP_UA_NAME` can only be set from inside the source
  (`project_flag`, "implied" origin only), not from a mozconfig. With vendor "Mozilla" and basename "Firefox",
  Orbis keeps its profiles in `%APPDATA%\Mozilla\Firefox` and `%LOCALAPPDATA%\Mozilla\Firefox`, the same place as
  an installed Firefox: one `profiles.ini` and one `installs.ini` for both, and either program can open, upgrade
  or lock the other's profiles (`MOZ_BLOCK_PROFILE_DOWNGRADE` is on). MSIX does not separate them: Firefox's
  dedicated-profile logic (`GetInstallHash`, `MaybeMakeDefaultDedicatedProfile`) writes to the same files when
  packaged. A trial build that only compiles is fine; starting it is not.
  Fix: `patches/0001-profile-folder-orbis.patch` (PR #4, merged), adds
  `imply_option("MOZ_APP_PROFILE", "Orbis")` (profiles in `%APPDATA%\Orbis` and `%LOCALAPPDATA%\Orbis`). The
  blocker is lifted only when that patch is applied to the build and its test passes: with Firefox installed,
  `%APPDATA%\Mozilla\Firefox\profiles.ini` and `installs.ini` stay byte-identical after Orbis runs (test plan in
  `docs/PATCHES.md`). Do not use `--with-app-basename=Orbis` instead: it changes the user agent to
  `Orbis/160.0` and the search configuration (rule 4 above).
- **STORE BLOCKER: executable version resource.** `browser/app/module.ver` (and `browser/app/pbproxy/module.ver`
  for `private_browsing.exe`) hard-codes `WIN32_MODULE_COMPANYNAME=Mozilla Corporation` and
  `WIN32_MODULE_TRADEMARKS=Firefox is a Trademark of The Mozilla Foundation.`, which `config/create_rc.py` writes
  into `orbis.exe`'s File Properties > Details. `ipc/app/module.ver` (`plugin-container.exe`) also says Mozilla
  Corporation. No build option changes them. Fix: `patches/0002-version-resource-orbis.patch` (PR #4) (company Orbis,
  empty trademark line). Still open after that patch: `create_rc.py` writes Mozilla's `LimitedAccessFeature`
  identity (see `docs/PATCHES.md`); to settle before any Store submission. The DLL defaults are a separate item
  below.
- **Not a Store blocker, fix before 1.0: DLL version resources.** `xul.dll`, `mozglue.dll`, `nss3.dll` and every
  other DLL or EXE without a `module.ver` get `config/create_rc.py`'s defaults: `CompanyName` "Mozilla Foundation"
  and `LegalTrademarks` "Mozilla" (`ProductName` and `FileDescription` are already "Orbis"). Why not blocking:
  the Store's listing, the installed app's name and the Start menu come from the MSIX `AppxManifest.xml` and
  `orbis.exe`, which patch 0002 fixed; Task Manager shows the process with `orbis.exe`'s resource; a DLL's version
  resource is visible only in File Properties > Details of a file inside the protected `WindowsApps` folder.
  The Store policies on accurate representation and intellectual property are about the listing and what the
  app shows; neither they nor the Windows App Certification Kit are known to read DLL version resources (not
  checked against the current policy text, and not confirmed with Microsoft). Why still fix it: "Mozilla
  Foundation" as the company of a binary Orbis built is not true, and it breaks the "no Mozilla names" rule in
  spirit. Fix: a small patch to `create_rc.py`'s two defaults (`Orbis`, empty), checked like 0002. Not done in
  this PR because it changes every binary's resource and needs the next build to check.
- **Not a Store blocker: langpack ID `langpack-en-US@firefox.mozilla.org`.** `mach package` also writes a separate
  en-US language pack, `dist/win64/xpi/orbis-160.0.en-US.langpack.xpi`, with the ID `langpack-en-US@` +
  `MOZ_LANGPACK_EID_HOST`, which `toolkit/moz.configure` fixes to `firefox.mozilla.org` (no build option). Why not
  blocking: that XPI is not in the package (the first build's `orbis-160.0.en-US.win64.zip` has no langpack;
  en-US is built into `omni.ja`), Orbis is English only and `ExtensionSettings` blocks the `locale` add-on type,
  and an add-on ID is an internal identifier, not a name a user sees (rule 5, like the built-in
  `newtab@mozilla.org`). It becomes an item only if Orbis ever ships language packs: then
  `mach repackage msix` would name them `langpack-<locale>@<app name>.mozilla.org.xpi`.
- **Store blocker for the MSIX step: Mozilla's MSIX `distribution.ini`.** `mach repackage msix` always adds
  `browser/installer/windows/msix/distribution/distribution.ini` (`id=mozilla-MSIX`, `about=Windows MSIX package`,
  "Author: Mozilla") before any `--distribution-dir`, and skips later files with the same name. `aboutDialog.js`
  shows `distribution.about` and `distribution.id` in the About dialog when both are set, so an MSIX built this
  way would show "Windows MSIX package" and "mozilla-MSIX - 1.0" (read from the source; no MSIX built yet). Fix
  with the MSIX PR: a patch to that file (Orbis id and about text, or no `[Global]` about) or an Orbis copy of
  the template. See `docs/BUILD.md`.
- **Still shared with Firefox, by design:** the enterprise-policy registry key
  `HKLM\SOFTWARE\Policies\Mozilla\Firefox` (and its HKCU twin): Firefox group policies set by an administrator also
  apply to Orbis. Other shared registry keys are listed in `docs/PATCHES.md`, "Still shared with Firefox".
- **About dialog text: fixed by `patches/0003-about-dialog-orbis.patch`, to check in the next build.** The first
  build's dialog said "Orbis is designed by Orbis, a global community working together to keep the Web open,
  public and accessible to all." (`community-2`, with `-vendor-short-name` "Orbis") and "Want to help? Make a
  donation or get involved!" (`helpus`), with links to `www.mozilla.org`, `about:credits`,
  `foundation.mozilla.org` and `www.mozilla.org/contribute`. The patch replaces `community-2` and `community-exp`
  with a new string, `orbis-about-description` (no links; the attribution stays in `trademarkInfo`), and removes
  `helpus`, `helpus-referrals2` and their links. Details in `docs/PATCHES.md`.
- **About dialog bottom links: removed by patch 0003; Orbis's own link to add later.** "Terms of Use" opened
  `www.mozilla.org/about/legal/terms/firefox/` and "Privacy Notice" `www.mozilla.org/privacy/firefox/`: Mozilla's
  documents for Firefox, not Orbis's. Patch 0003 removes both. When Orbis has its own privacy policy (the Store
  requires one), a later patch adds a link to it. "Licensing Information" (`about:license`) stays.
- **New-tab default top sites: fixed by a pref, to check in the next build.** The first build showed "Add-ons for
  Firefox" with the Firefox logo as a default top site, from the Remote Settings `top-sites` collection.
  `orbis.cfg` now locks `browser.newtabpage.activity-stream.default.sites` to `""`: no default top sites
  (Shibi's decision; `docs/SETTINGS.md`).
- **`about:support` and the app info say "Firefox" and "Mozilla", by design (rule 4).** `application.ini` has
  `Name=Firefox` and `Vendor=Mozilla` (seen in the first build; `MOZ_APP_BASENAME` and the vendor implied by
  `browser/moz.configure`), so `Services.appinfo.name` is "Firefox" and `Services.appinfo.vendor` "Mozilla"
  (`checks-idle.json`). `about:support` shows the name in "Application Basics" > "Name" (`Troubleshoot.sys.mjs`
  reads `Services.appinfo.name`); a vendor is shown there only when `app.support.vendor` is set, which Orbis does
  not set. Extensions see the same values through `runtime.getBrowserInfo()`. Changing them would change the
  user agent and the search configuration (rule 4) and needs a patch; `about:support` is a troubleshooting page,
  not a product name. Revisit only if the Store review objects.
- **Real artwork and Store tiles (PR 9).** Replace every placeholder; keep the same file names and sizes.
- **Strings outside the branding folder (PR 9).** Some Firefox pages name Mozilla or Firefox directly, for example
  `browser/base/content/overrides/app-license.html` ("made available to you by the Mozilla Project"). Audit them
  and override or patch the ones a user sees. `-vendor-short-name` is now "Orbis", so check every string that uses
  it still says something true.
- **`firefox.VisualElementsManifest.xml`.** Windows reads `<exe name>.VisualElementsManifest.xml`; with `orbis.exe`
  the file may need renaming for the classic Start menu tile. MSIX uses its own tile images, so this may not
  matter. Unverified.
- **Icons with PNG-compressed entries.** The generated `.ico` files store PNG images (valid since Windows Vista).
  That the build's resource compiler accepts them is unverified until the first build.
- **The name "Orbis"** in the Microsoft Store and as a trademark: not checked.
