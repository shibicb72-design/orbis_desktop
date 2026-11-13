# Orbis Desktop: Microsoft Store submission

Text to paste into Partner Center, what still blocks a submission, and the Store policy risks. Shibi owns the
Store account and does every upload and publish (`AGENTS.md`); this file only prepares the text. How the package
is made: `docs/MSIX.md`.

Store name: **Orbis Browser** (reserved by Shibi). Store ID `9N9C8WTZRJ3P`,
<https://apps.microsoft.com/detail/9N9C8WTZRJ3P>.

## Partner Center identity values

In Partner Center: the app "Orbis Browser" > **Product management** > **Product identity**. Copy each field
below exactly (case and spaces matter) into `packaging/msix-config.json`. Shibi sent them on 2026-11-12; they
are in the file now. They are public, not secrets: every installed package's manifest shows them.

| Partner Center field (Product identity) | Value | Goes to (`packaging/msix-config.json`) | Ends up in the MSIX |
|---|---|---|---|
| Package/Identity/Name | `shibicb72.OrbisBrowser` | `identityName` | `AppxManifest.xml` `Package/Identity/@Name`; `make-msix.ps1` splits it into mach's `--vendor shibicb72` and checks that the rest is `displayName` without spaces |
| Package/Identity/Publisher | `CN=85F6A8A7-CE41-468D-8AF2-56079E715950` | `publisher` | `Package/Identity/@Publisher` (mach `--publisher`); the Store signs with it |
| Package/Properties/PublisherDisplayName | `shibicb72` | `publisherDisplayName` | `Package/Properties/PublisherDisplayName` (mach `--publisher-display-name`) |
| Package Family Name (PFN) | `shibicb72.OrbisBrowser_bcchdm3mrcmtt` | `packageFamilyName` | Not written: `make-msix.ps1` computes it from Name and Publisher and refuses a mismatch (catches a typo) |
| The reserved app name | `Orbis Browser` | `displayName`, and `brandFullName` / `-brand-full-name` in `overlay/browser/branding/orbis/locales/en-US/` | `Package/Properties/DisplayName` and `Description` (from `brandFullName`), tile and Start menu name, install folder `Orbis Browser Package Root` |

Not needed in the repository: the Store ID (`9N9C8WTZRJ3P`, for the listing link only), "Package SID" and any
other field on that page. Check after editing:

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make-msix.ps1 -ConfigOnly -RequireStoreIdentity
```

## Restricted capability: `runFullTrust`

Partner Center asks why the package declares a restricted capability. Paste this text unchanged:

> Orbis Browser is a desktop web browser built on the open-source Gecko engine (Mozilla Firefox source, current release
> version), packaged as MSIX. It is a classic Win32 application (EntryPoint Windows.FullTrustApplication) and
> cannot run in the AppContainer sandbox, so it requires runFullTrust. The capability is used only for normal
> browser functions: starting the browser's own sandboxed content, GPU, network and media child processes;
> reading and writing the user's profile, and files the user chooses to open or download; and registering as a
> handler for http, https, mailto and web file types. runFullTrust is the only capability declared. The app
> installs no drivers or NT services, does not run elevated, and contains no self-updater, update service or
> crash reporter; updates come only through the Microsoft Store. The LaunchOnLogin startup task is disabled by
> default and is enabled only by the user.

## Notes for certification

Paste the justification above, followed by this addendum, unchanged:

> On first run Orbis shows one screen that offers the uBlock Origin content blocker ("Install uBlock Origin ad
> blocker", checked by default). It is downloaded from addons.mozilla.org only if the user continues with the
> box checked and confirms the browser's add-on permission prompt; with the box unchecked nothing is downloaded
> or installed, and the screen states that phishing and malware protection is then off. The screen is shown
> again at the next start until the user unchecks the box or the extension is installed (for example if the
> screen is closed without an answer, or the permission prompt is cancelled); after that it is not shown again.
> The extension is not included in the package. Telemetry is disabled.

The Store description should say the same: uBlock Origin is offered at first run and downloaded from
addons.mozilla.org if the user agrees (see policy 10.1.5 under "Risks").

## Privacy policy URL (policy 10.5.1)

<https://shibicb72-design.github.io/orbis_desktop/privacy.html> (source: `docs/privacy.html`; see "Risks", policy 10.5.1).

## Blockers before the first submission

In this order:

1. **Name reserved: done.** Shibi reserved "Orbis Browser" (not "Orbis"). The branding's full name, the
   tile name and `displayName` now say "Orbis Browser" (`docs/BRANDING.md`).
2. **Real identity values: done.** In `packaging/msix-config.json` (table above). Build every upload with
   `make-msix.ps1 -RequireStoreIdentity` (`docs/MSIX.md`). The first Store package was built this way on
   2026-11-12 (an incremental build was enough to pick up `brandFullName=Orbis Browser`); not uploaded. It was
   replaced the same day by a package of main `f480cd8` with the new About text and the Orbit art
   (`docs/MSIX.md`); also not uploaded.
3. **Real artwork: done.** Every icon, tile and Store logo is the original "Orbit" art (`docs/BRANDING.md`),
   checked in the package of main `f480cd8`. Still open: the manifest's tile background `#20123A` is Firefox
   purple. The Orbit tiles are opaque, so it does not show on them, but it may show behind the plated
   `Square44x44Logo` (`docs/BRANDING.md`, open items).
4. **An install test that proves the policies and AutoConfig work inside the MSIX.** Nothing has been installed
   yet. The test must show, in the installed package: `policies.json` active (`about:policies`), the
   `orbis.cfg` prefs locked, the uBlock Origin consent screen on first run (uBlock Origin installed after
   "Continue" with the box checked, nothing installed with it unchecked, the screen back after closing it
   unanswered or cancelling Firefox's prompt, no Start-menu re-pin on that repeated ask), and no Mozilla
   `distribution.ini`.
   Method: option 4, then option 1 in `docs/MSIX.md`, "Local install test".

## Store policy 10.2.1: engine currency

A browser must use an engine no more than 2 major versions behind the current release of that engine. For
Orbis that means Firefox: rebase on **every Firefox major release** (about every four weeks), not only when the
gap reaches 2. The Orbis rule is stricter still: follow the release-candidate tag as soon as it appears
(`AGENTS.md`, "Engine currency"; `docs/UPDATING.md`). `scripts/check-firefox-currency.ps1` fails when the pin
falls behind. Each rebase raises the MSIX version (`docs/MSIX.md`, "Version").

The same policy also says that known security issues must be patched "in a more timely fashion". That clause
covers Firefox's point releases (`X.Y.1`, `X.Y.2`, often security fixes): ship each one promptly too, with an
`orbisRevision` reset and a new MSIX version, not only the major releases.

## Risks

Policy numbers and quotes are from the Microsoft Store Policies **v7.20, effective 2026-10-22**. Text in quotes
is the policy's wording; the rest summarises it.

- **Policy 10.1.5 (add-ons): met.** The policy allows a product to offer add-ons only "with user consent and
  after initial download of the primary product". Shibi decided (2026-11-12) to ask, as Orbis for Android does:
  Orbis installs nothing by policy (`ExtensionSettings` only allows uBlock Origin), and the first window of a
  new profile shows a consent screen (`docs/SETTINGS.md`, "First run: uBlock Origin consent screen"). uBlock
  Origin is downloaded from addons.mozilla.org only after the user continues with "Install uBlock Origin ad
  blocker" checked (the default) and accepts Firefox's own "Add uBlock Origin?" permission prompt; with the box
  unchecked nothing is downloaded. The screen comes back at each start until the user declines or uBlock Origin
  is installed (closed unanswered, or accepted but not installed: Firefox's prompt left or cancelled, download
  failed), and never after that. The extension is not in the package (no
  XPI is shipped). Checked by `scripts/check-settings.py` (no silent install in `policies.json`, the install
  only behind the checkbox) and `scripts/verify-build.py consent` (on a test build, see `docs/BUILD.md`). A
  reviewer may still ask why the box is checked by default; the answer is that nothing is downloaded until the
  user clicks Continue on that screen, and nothing is installed until the user also accepts the permission
  prompt.
- **Policy 10.2.2 (dynamic code).** A product must not download or run code that changes its described
  functionality. uBlock Origin is downloaded after install, and its filter lists update from the network. Be
  ready to explain that it is a declared, signed browser extension (`MOZ_REQUIRE_SIGNING` stays on) that
  delivers the content blocking the description promises.
- **Policy 10.2.3 (secondary software).** Secondary software installed with the product must enhance the
  product. uBlock Origin is the content blocker the description promises; the description must say so, so
  that it reads as part of the product and not as bundled software.
- **Safe Browsing off versus policy 10.2 (security).** Google Safe Browsing (phishing, malware and download
  checks) is locked off (`docs/SETTINGS.md`, owner decision 2026-11-12). A reviewer may see a browser without
  malicious-site protection as a security weakness. Be ready to explain the choice (privacy: these checks send
  data to Google), and say what protects users instead: uBlock Origin's filter lists, and possibly Windows'
  SmartScreen check when a downloaded program is started (unverified: not checked for programs downloaded by
  Orbis). uBlock Origin is now the user's choice, so a user who declines it has no phishing or malware site
  protection in Orbis. Shibi decided (2026-11-12) to warn and ask again: unchecking the box shows "Without uBlock
  Origin, phishing and malware protection is off. Orbis does not use Google Safe Browsing. ..." before Continue,
  and the screen comes back at the next start until the user declines or uBlock Origin is installed. The risk for 10.2 stays for users who decline;
  the warning makes it an informed choice.
- **A privacy policy URL is required (policy 10.5.1).** Under 10.5.1, Desktop Bridge and Win32 products always
  need a privacy policy, whatever data they collect. Orbis is one. Its policy is `docs/privacy.html`, published by
  GitHub Pages (source: branch `main`, folder `/docs`) at
  <https://shibicb72-design.github.io/orbis_desktop/privacy.html>. Paste that URL into Partner Center
  (the app > **Store listing** > **Privacy policy URL**). Check that the URL opens before you submit: Pages must be
  turned on first. The policy discloses the network calls that remain (`docs/SETTINGS.md`) and the uBlock Origin
  consent and download; every statement in it comes from `docs/SETTINGS.md`. When a row of "Network calls that
  remain" changes, change the policy and its effective date in the same PR. The About dialog link to it is still
  to add (`docs/BRANDING.md`).
