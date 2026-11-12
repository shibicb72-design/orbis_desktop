# Orbis Desktop: Microsoft Store submission

Text to paste into Partner Center, what still blocks a submission, and the Store policy risks. Shibi owns the
Store account and does every upload and publish (`AGENTS.md`); this file only prepares the text. How the package
is made: `docs/MSIX.md`.

## Restricted capability: `runFullTrust`

Partner Center asks why the package declares a restricted capability. Paste this text unchanged:

> Orbis is a desktop web browser built on the open-source Gecko engine (Mozilla Firefox source, current release
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

> On first run Orbis installs the uBlock Origin extension from addons.mozilla.org (stated in the description),
> and telemetry is disabled.

The Store description must then really state the uBlock Origin install. That is disclosure, not consent:
see policy 10.1.5 under "Risks".

## Blockers before the first submission

In this order:

1. **Reserve the name "Orbis" in Partner Center, before anything else.** Everything below depends on it, and
   the name may be taken. If "Orbis" is not available, the product name changes everywhere (branding,
   `displayName` in `packaging/msix-config.json`, the identity suffix that `make-msix.ps1` checks).
2. **Real identity values.** Copy Partner Center's Package/Identity/Name, Package/Identity/Publisher and
   Package/Properties/PublisherDisplayName into `packaging/msix-config.json` (now `TODO-STORE`), and build with
   `make-msix.ps1 -RequireStoreIdentity`, which refuses placeholders (`docs/MSIX.md`).
3. **Real artwork.** Every icon, tile and Store logo is a TODO placeholder (`docs/BRANDING.md`, PR 9), and the
   tile background `#20123A` is Firefox purple.
4. **An install test that proves the policies and AutoConfig work inside the MSIX.** Nothing has been installed
   yet. The test must show, in the installed package: `policies.json` active (`about:policies`), the
   `orbis.cfg` prefs locked, uBlock Origin installed, and no Mozilla `distribution.ini`. Method: option 4, then
   option 1 in `docs/MSIX.md`, "Local install test".

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

- **uBlock Origin auto-install versus policy 10.1.5. The risk remains.** The policy allows a product to offer
  add-ons only "with user consent and after initial download of the primary product". Orbis installs uBlock
  Origin silently on first run (`ExtensionSettings` in `policies.json`): there is no consent step. Stating it in
  the Store description and the certification notes (above) is **disclosure, not consent**, so it does not
  remove the risk. The risk stays unless Orbis asks at first run (for example a first-run prompt, with "no"
  leaving uBlock Origin uninstalled). **Shibi decides** whether to add a consent step or to submit as is and
  accept the risk. The extension comes from addons.mozilla.org, not from the package (no XPI is shipped).
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
  Orbis).
- **A privacy policy URL is required (policy 10.5.1).** Under 10.5.1, Desktop Bridge and Win32 products always
  need a privacy policy, whatever data they collect. Orbis is one, and has no privacy policy yet. It must
  disclose the network calls that remain (`docs/SETTINGS.md`, for example the push websocket and translation
  model downloads from Mozilla) and the uBlock Origin download. The About dialog link to it is still to add
  (`docs/BRANDING.md`).
