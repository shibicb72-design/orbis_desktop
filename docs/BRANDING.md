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
   `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:160.0) Gecko/20100101 Firefox/160.0` (read from the source, not
   yet observed in a build).
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
| `branding.nsi` | `BrandFullName`, `CompanyName`, URLs | `Orbis`, the Orbis repository (no NSIS installer is shipped) |
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

- **Profile folder (needs a patch, PR 5).** `browser/moz.configure` hard-codes
  `imply_option("MOZ_APP_VENDOR", "Mozilla")`, and `MOZ_APP_VENDOR`, `MOZ_APP_PROFILE` and `MOZ_APP_UA_NAME` can
  only be set from inside the source (`project_flag`, "implied" origin only), not from a mozconfig. With vendor
  "Mozilla" and basename "Firefox", Orbis would keep its profiles in `%APPDATA%\Mozilla\Firefox`, the same place as
  an installed Firefox. A one-line patch in `patches/` (setting `MOZ_APP_PROFILE` or the vendor) is the likely fix;
  whether MSIX file virtualisation already separates them is unverified.
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
