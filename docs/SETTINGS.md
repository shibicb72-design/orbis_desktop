# Orbis Desktop settings

Every setting Orbis changes from Firefox 160's defaults, with its value, whether the user can change it, and why.
Files:

- `overlay/distribution/policies.json`: Firefox enterprise policies. Shown to the user at `about:policies`.
- `overlay/orbis.cfg`: AutoConfig prefs that no policy covers. Loaded by `overlay/defaults/pref/autoconfig.js`.

Words used in the tables:

- **Locked**: the user cannot change it, not in Settings and not in `about:config`.
- **Default**: Orbis's starting value; the user can change it and the change is kept.
- **Source**: where the pref is defined in the pinned Firefox 160 source (`StaticPrefList.yaml`, `all.js`,
  `firefox.js`), or "code: file" when no pref file defines it and Firefox code reads it by that exact name.
  Policy names and values are checked against `policies-schema.json` at the same commit.

`python -I scripts/check-settings.py` fails if a pref or policy here does not exist in the pinned source, if a
value has the wrong type or is not allowed by the policy schema, or if a setting has no row in this file.

## Defaults: decided by Shibi, and pending Shibi's OK

Shibi decided (2026-11-12): Microsoft Store only, release channel, Google Safe Browsing off, uBlock Origin offered
on a first-run screen (on by default, installed only if the user keeps it on) with Orbis's filter lists enforced at
every launch once installed (including "Phishing URL Blocklist"), push websocket kept, AMO metadata cache off, no
servers, accounts, sync, analytics, telemetry or studies, English only.
See "Decided by Shibi" below.

### Pending Shibi's OK

Shibi has not explicitly approved these. They follow Fable's recommended defaults:

| Choice | Orbis default |
|---|---|
| Telemetry, studies, Firefox accounts and sync, sponsored content, AI chatbot | Off and **locked** |
| Enhanced Tracking Protection | Strict, **user can change** |
| HTTPS-only mode | On in all windows, **user can change** |
| Search engine | DuckDuckGo, **user can change** |
| DRM (Widevine, Encrypted Media Extensions) | Off, user can turn it on |
| DNS over HTTPS | Off, user can turn it on |
| Captive-portal and connectivity checks | Off, user can turn them on. Hotel, airport and café Wi-Fi login pages will **not open by themselves**; the user opens any page to reach them, or turns the check back on |
| `about:config` | Open (no policy blocks it) |

### Decided by Shibi (2026-11-12)

| Choice | Decision | State in this branch |
|---|---|---|
| Google Safe Browsing | Off | Off, every Google endpoint blanked (`orbis.cfg`); phishing and malware protection come from uBlock Origin's lists |
| uBlock Origin | Offered at first run, as on Android: "Install uBlock Origin ad blocker", on by default; one click on Continue installs it from addons.mozilla.org, and nothing is installed if the user turns it off (Store policy 10.1.5). Replaces the earlier automatic install | First-run screen in `about:welcome` (`browser.aboutwelcome.screens`, `orbis.cfg`); `ExtensionSettings` only allows uBlock Origin. See "First run: uBlock Origin consent screen" |
| uBlock Origin filter lists | Option C: Orbis's list set, **enforced at every launch**. A user's list changes reset at the next start | `3rdparty` `toOverwrite.filterLists`, re-applied by uBlock Origin at every launch. Options A and B were rejected (below) |
| Push websocket (`push.services.mozilla.com`) | Stays on | On (Firefox default) and disclosed in "Network calls that remain" and the privacy policy |
| AMO metadata cache (`extensions.getAddons.cache.enabled`) | Off | false, locked (`orbis.cfg`) |
| New-tab default top sites (`browser.newtabpage.activity-stream.default.sites`) | None | `""`, locked (`orbis.cfg`) |

Why the lists are enforced rather than set once: uBlock Origin cannot do "first run only" from policy (read from
uBlock Origin's current `src/js/start.js`, `storage.js` and `assets.js`):

- `restoreAdminSettings()` runs at every start. Both list settings it reads, `toOverwrite.filterLists` and
  `adminSettings.selectedFilterLists`, are written to storage every time; neither checks for a first run.
- The only first-run path is `loadSelectedFilterLists()`: when storage has no list selection, uBlock Origin selects
  every list in its `assets.json` that is not marked `off`, plus regional lists for the browser language. After
  that it never touches the selection again, except for changes to its own default set.
- `adminSettings.assetsBootstrapLocation` can point that first run at a different `assets.json`, but it must be an
  `http(s)` URL (a `data:` URL or a file inside the browser does not work). And when uBlock Origin later updates
  `assets.json` from its own server, it removes from the selection every list that was a default in the old
  file and is not one in the new file. The three Orbis extras would be switched off again at that update.

Chosen (Shibi, 2026-11-12):

- **C. Keep `toOverwrite`, enforced at every launch.** Orbis's lists are always on, so the Phishing URL Blocklist
  that stands in for Google Safe Browsing cannot stay off. A user can change the lists for the current session;
  the change is reset at the next start. Regional lists are not selected automatically.

Rejected alternatives:

- **A. Orbis hosts its own `assets.json`** (a copy of uBlock Origin's file with the three extras switched on and its
  own update URL pointing back at the Orbis copy, set by `adminSettings.assetsBootstrapLocation`). Rejected: it
  needs a server. Every install would fetch an Orbis-run file about every 13 days, which breaks "no servers";
  Orbis would have to copy uBlock Origin's changes into it; and whoever can change that file can change every
  user's lists, including which ones uBlock Origin trusts, without a release.
- **B. Drop `3rdparty`** (uBlock Origin chooses its own default lists at first run, plus regional lists, and the
  user's changes are kept). Rejected: phishing protection would be off by default. "Phishing URL Blocklist" and
  the two cookie-notice lists are not among uBlock Origin's defaults, and the phishing list is what replaces Google
  Safe Browsing.

## Differences from Orbis for Android

Read from `work-orbis` (`engine/GeckoEngineImpl.kt`, `settings/BrowserSettings.kt`, `engine/SearchEngine.kt`).

| Area | Android | Desktop | Why |
|---|---|---|---|
| Google Safe Browsing | On (`ContentBlocking.SafeBrowsing.DEFAULT`) | Off, Google endpoints blanked | Owner decision 2026-11-12 |
| `about:config` | Blocked (`aboutConfigEnabled(false)`) | Open | Desktop convention; locked prefs stay locked there. Pending OK |
| Tracking-protection level | Strict, fixed; per-site exceptions only | Strict on first start; the user may switch to Standard or Custom | "Adjustable" ETP. Pending OK |
| uBlock Origin | From AMO after the user agrees (switch on by default); uBlock Origin's default lists | From AMO after the user agrees (checkbox on by default, then Firefox's own "Add uBlock Origin?" permission prompt); default lists plus "Phishing URL Blocklist", enforced at every start | Owner decisions 2026-11-12 (consent screen as on Android; enforced lists). Desktop shows a checkbox, not a switch: Firefox's onboarding page has no switch control |
| Search engines offered | DuckDuckGo (default), Google, Bing, Brave, Startpage | DuckDuckGo (default), Brave Search and Startpage added, plus Firefox's own built-in list for the user's region (for example Google, Bing, Wikipedia, eBay, Perplexity) | Firefox's built-in list is left alone; removing engines was not decided |
| DRM | GeckoView default (Orbis sets nothing) | Off, user can enable | Pending OK |
| Captive-portal check | GeckoView default (Orbis sets nothing) | Off, user can enable | Pending OK |
| DNS over HTTPS | GeckoView default (Orbis sets nothing) | Off (`network.trr.mode` 5, which also stops Mozilla's DoH rollout) | Pending OK |

Same on both: ETP Strict with strict social-tracking protection; third-party cookies isolated per site in normal
and private tabs (Strict includes `cookieBehavior5` and `cookieBehaviorPBM5`); HTTPS-only in all tabs by default;
DuckDuckGo default; search suggestions on except in private windows (the Firefox default on desktop); no
telemetry, no accounts, no AI chat.

## Policies (`policies.json`)

| Policy | Value | Locked? | Reason |
|---|---|---|---|
| `DisableTelemetry` | `true` | Locked | No telemetry. Locks `datareporting.healthreport.uploadEnabled`, `datareporting.policy.dataSubmissionEnabled`, `datareporting.usage.uploadEnabled`, `toolkit.telemetry.archive.enabled` |
| `DisableFirefoxStudies` | `true` | Locked | No studies (Shield/Normandy) |
| `DisableRemoteImprovements` | `true` | Locked | No remote Nimbus rollouts that change the browser between updates |
| (`DisableAccounts`, not set) | - | - | Replaced by `identity.fxaccounts.enabled` locked false in `orbis.cfg`. In Firefox 160 `DisableAccounts` (and `DisableFirefoxAccounts`) lock that pref and also lock `browser.aboutwelcome.enabled` to false, which would remove the uBlock Origin consent screen. The pref is the policy's only other effect (`Policies.sys.mjs`). `check-settings.py` fails if either policy comes back |
| `IPProtectionAvailable` | `false` | Locked | The built-in VPN needs a Mozilla account and Mozilla's servers |
| `DisableAppUpdate` | `true` | Locked | The Microsoft Store updates Orbis. The updater is also not built (PR 4) |
| `DisableSystemAddonUpdate` | `true` | Locked | `DisableAppUpdate` does not cover system add-ons: with `extensions.systemAddon.update.enabled` (true in firefox.js) Firefox polls `aus5.mozilla.org` for new system add-ons outside the Store. The policy disallows the `SysAddonUpdate` feature, which `AddonManager.systemUpdateEnabled` checks. The built-in system add-ons ship in the package and update with it |
| `DisableDefaultBrowserAgent` | `true` | Locked | No background agent. Also not built (PR 4) |
| `DontCheckDefaultBrowser` | `true` | Locked | No "make default" prompt at every start; the user can still make Orbis the default in Settings |
| `DisableFeedbackCommands` | `true` | Locked | Removes "Report deceptive site" (goes to Google) and "Submit feedback" (Mozilla) |
| `SkipTermsOfUse` | `true` | Locked | Mozilla's Terms of Use prompt does not apply to Orbis |
| (`OverrideFirstRunPage`, not set) | - | - | Any value of this policy also locks `browser.aboutwelcome.enabled` to false. The first-run page is set by `orbis.cfg` instead (`startup.homepage_welcome_url`): Orbis's own consent screen, not Mozilla's onboarding |
| `OverridePostUpdatePage` | `""` | Locked | No Mozilla "what's new" page after updates |
| `NoDefaultBookmarks` | `true` | Locked | Firefox's default bookmarks point at Mozilla sites |
| `FirefoxHome` | `SponsoredTopSites`, `Stories`, `SponsoredStories`, `Weather` false; `Locked` | Locked | No sponsored or recommended content on the new-tab page; stories and weather come from Mozilla's servers |
| `FirefoxSuggest` | `WebSuggestions`, `SponsoredSuggestions`, `ImproveSuggest`, `OnlineEnabled` false; `Locked` | Locked | No sponsored or Mozilla-served suggestions in the address bar |
| `UserMessaging` | `ExtensionRecommendations`, `FeatureRecommendations`, `UrlbarInterventions`, `MoreFromMozilla`, `FirefoxLabs` false; `Locked` | Locked | No Mozilla marketing messages. `SkipOnboarding` is not set: it would switch off `about:welcome`, which shows the uBlock Origin consent screen; Mozilla's own onboarding screens are replaced by `browser.aboutwelcome.screens` instead. Firefox Labs is opt-in Nimbus experiments. Side effect: `FeatureRecommendations` false with `Locked` also sets and locks `browser.translations.mostRecentTargetLanguages` to the user's first web language, so the translation panel skips its intro and its "recent languages" list stays fixed to that language |
| `AIControls` | `Default` blocked and locked; `Translations` available, not locked | AI features locked off; translation is a default | No AI chatbot (locked). The same `Default` also blocks link-preview key points, smart tab groups, smart window, PDF alt text and speech recognition. Translation runs on the device; its models download from Mozilla (to disclose in the privacy policy) |
| `HttpsOnlyMode` | `"enabled"` | Default | HTTPS-only in normal and private windows, as on Android. The user can turn it off or add exceptions |
| `EncryptedMediaExtensions` | `Enabled` false | Default | DRM is a closed Google component downloaded on demand. Netflix and similar sites will not play until the user enables it |
| `DNSOverHTTPS` | `Enabled` false | Default | No third-party DNS resolver by default. Sets `network.trr.mode` to 5 ("off by choice"), which also stops Mozilla's regional DoH rollout. The user can turn DoH on |
| `SearchEngines` | `Default` DuckDuckGo; `Add` Brave Search and Startpage | Default | Same default and engines as Android. The added engines have no icon URL (so no request to fetch one) and no suggestion URL (so no search suggestions from them) |
| `ExtensionSettings` | `*`: allowed types extension, theme, dictionary, sitepermission. `uBlock0@raymondhill.net`: `allowed`, `private_browsing` true | Language packs blocked; uBlock Origin is allowed, not installed | English only (no `locale` type). No policy installs uBlock Origin (Store policy 10.1.5): the user chooses on the first-run screen, or installs it later. Once installed it works in private windows, and the user can disable or remove it. It is downloaded from AMO, not bundled (GPL-3.0). `check-settings.py` fails on any `force_installed` or `normal_installed` entry |
| `3rdparty` | uBlock Origin `toOverwrite.filterLists`: `user-filters`, `ublock-filters`, `ublock-badware`, `ublock-privacy`, `ublock-unbreak`, `ublock-quick-fixes`, `easylist`, `easyprivacy`, `urlhaus-1`, `plowe-0`, `curben-phishing`, `fanboy-cookiemonster`, `ublock-cookies-easylist` | Enforced: re-applied at every start, so a user's list changes reset at the next start (Shibi's decision, option C; see "Decided by Shibi") | uBlock Origin's own defaults plus "Phishing URL Blocklist" (`curben-phishing`), which stands in for Google Safe Browsing's phishing protection. Malware: `urlhaus-1` and `ublock-badware`. Cookie notices (plan C.2): uBlock Origin's "EasyList/uBO – Cookie Notices" pair, `fanboy-cookiemonster` and `ublock-cookies-easylist`, both off by default in uBlock Origin; the AdGuard pair is not added, to avoid double filtering. These lists hide or block notices; they do not click "accept" or "reject". uBlock Origin applies `toOverwrite` at every launch, so a user's list changes last only until the next start. It applies whenever uBlock Origin is installed, from the consent screen or later by hand; without uBlock Origin it does nothing |

## Prefs (`orbis.cfg`)

### Telemetry, studies, crash reports: locked

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `toolkit.telemetry.unified` | false | Locked | Telemetry off | all.js |
| `toolkit.telemetry.enabled` | false | Locked | Telemetry off | code: TelemetryControllerBase.sys.mjs |
| `toolkit.telemetry.server` | `"data:,"` | Locked | No endpoint to send to | all.js |
| `toolkit.telemetry.newProfilePing.enabled` | false | Locked | No new-profile ping | firefox.js |
| `toolkit.telemetry.updatePing.enabled` | false | Locked | No update ping | code: TelemetryUtils.sys.mjs |
| `toolkit.telemetry.firstShutdownPing.enabled` | false | Locked | No first-shutdown ping | firefox.js |
| `toolkit.telemetry.shutdownPingSender.enabled` | false | Locked | No shutdown ping sender | firefox.js |
| `toolkit.telemetry.bhrPing.enabled` | false | Locked | No hang reports | firefox.js |
| `toolkit.telemetry.dap.leader.url` | `""` | Locked | No Distributed Aggregation Protocol reports (leader at divviup.org) | all.js |
| `toolkit.telemetry.dap.helper.url` | `""` | Locked | Same (Mozilla's DAP helper) | all.js |
| `browser.newtabpage.activity-stream.telemetry` | false | Locked | No new-tab telemetry | code: AboutWelcomeTelemetry.sys.mjs |
| `browser.search.serpEventTelemetryCategorization.enabled` | false | Locked | No search-result categorisation telemetry | firefox.js |
| `browser.discovery.enabled` | false | Locked | No add-on recommendations based on telemetry data | firefox.js |
| `browser.tabs.crashReporting.sendReport` | false | Locked | No tab crash reports (the crash reporter is also not built, PR 4) | firefox.js |
| `browser.crashReports.unsubmittedCheck.autoSubmit2` | false | Locked | No automatic crash-report submission | firefox.js |
| `app.normandy.enabled` | false | Locked | No Normandy studies | firefox.js |
| `app.normandy.api_url` | `""` | Locked | No Normandy endpoint | firefox.js |
| `app.shield.optoutstudies.enabled` | false | Locked | No opt-out studies | firefox.js (both branches of `#ifdef MOZ_DATA_REPORTING`) |
| `nimbus.rollouts.enabled` | false | Locked | No Nimbus rollouts (with the `DisableRemoteImprovements` policy) | firefox.js |

### Google Safe Browsing: locked off

Owner decision 2026-11-12. Protection comes from uBlock Origin's malware lists and its Phishing URL Blocklist
(`3rdparty` above). Windows SmartScreen is not touched. The endpoints are blanked as LibreWolf does, so that a list
switched back on by a future Firefox version still cannot reach Google. The "mozilla" provider, which tracking
protection uses, is not changed.

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `browser.safebrowsing.malware.enabled` | false | Locked | No Google malware list | StaticPrefList.yaml |
| `browser.safebrowsing.phishing.enabled` | false | Locked | No Google phishing list | StaticPrefList.yaml |
| `browser.safebrowsing.downloads.enabled` | false | Locked | No Google download checks | all.js |
| `browser.safebrowsing.downloads.remote.enabled` | false | Locked | No download reputation requests (these send the full download URL to Google) | all.js |
| `browser.safebrowsing.downloads.remote.url` | `""` | Locked | Endpoint blanked | all.js |
| `browser.safebrowsing.downloads.remote.block_potentially_unwanted` | false | Locked | Depends on the remote check | all.js |
| `browser.safebrowsing.downloads.remote.block_uncommon` | false | Locked | Depends on the remote check | all.js |
| `browser.safebrowsing.provider.google.updateURL` | `""` | Locked | v2.2 endpoint blanked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google.gethashURL` | `""` | Locked | v2.2 endpoint blanked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google4.updateURL` | `""` | Locked | v4 endpoint blanked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google4.gethashURL` | `""` | Locked | v4 endpoint blanked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google4.dataSharingURL` | `""` | Locked | v4 data-sharing endpoint blanked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google4.dataSharing.enabled` | false | Locked | Already false in Firefox; locked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google5.enabled` | false | Locked | v5 provider (the one Firefox 160 uses) off | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google5.updateURL` | `""` | Locked | v5 endpoint blanked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.provider.google5.gethashURL` | `""` | Locked | v5 endpoint blanked | all.js (`#ifndef MOZ_WIDGET_ANDROID`) |
| `browser.safebrowsing.realTime.enabled` | false | Locked | Real-time URL lookups; Nightly-only in 160, locked so a later release cannot turn them on | StaticPrefList.yaml |
| `browser.safebrowsing.globalCache.enabled` | false | Locked | Same, for the global lookup cache | StaticPrefList.yaml |

### Widevine from Google's update service: locked off

`GMPInstallManager.checkForAddons()` calls `adjustForChromiumUpdateService()` before it filters out Widevine when
DRM is off. With these prefs true (the Windows default) Firefox asks `update.googleapis.com/service/update2/crx`
about Widevine once a day even with DRM off. Locked false, Widevine (if the user turns DRM on) comes only through
Mozilla's GMP manifest.

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `media.gmp-widevinecdm.allow-chromium-update` | false | Locked | No daily request to Google's component updater | firefox.js (`#ifdef MOZ_WIDEVINE_EME`) |
| `media.gmp-widevinecdm-l1.allow-chromium-update` | false | Locked | Same, for the hardware-backed (L1) Widevine | firefox.js (`#if defined(MOZ_WMF_CDM) && defined(_M_AMD64)`) |

### Other Mozilla services: locked off

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `security.certerrors.mitm.priming.enabled` | false | Locked | On a certificate error page Firefox would fetch `mitmdetection.services.mozilla.com` to detect interception software | firefox.js |
| `browser.topsites.contile.enabled` | false | Locked | Contile serves sponsored top sites from Mozilla's server; `FirefoxHome` already hides them, this stops the fetch too | firefox.js |
| `browser.newtabpage.activity-stream.default.sites` | `""` | Locked | Shibi, 2026-11-12: no default top sites on the new-tab page; the tiles fill only from the user's own history and pins. Why: Firefox 160 takes its defaults from the Remote Settings `top-sites` collection; with region lookup off (below) no region is known, and that collection then adds "Add-ons for Firefox" (`addons.mozilla.org`, shown with the Firefox logo). Read in the source: when this pref is locked, `_readDefaults` (`TopSitesFeed.sys.mjs` for the new-tab page, `TopSites.sys.mjs` for the address bar) calls `refreshDefaults` with its value and returns before `_getRemoteConfig` (Remote Settings) and `_readContile`; `refreshDefaults("")` empties the default list and adds nothing, so there are zero default tiles. Locking also keeps Activity Stream from writing its region default into the pref (libpref does not change a locked default). Contile's own fetch stays off through `FirefoxHome` (`SponsoredTopSites` false) and `browser.topsites.contile.enabled`. Only the defaults are locked: the user can still pin, edit and remove top sites | code: browser/extensions/newtab/lib/TopSitesFeed.sys.mjs, browser/components/topsites/TopSites.sys.mjs |
| `extensions.getAddons.showPane` | false | Locked | No "Recommendations" pane in `about:addons` (content from addons.mozilla.org) | code: toolkit/mozapps/extensions/content/aboutaddons-utils.mjs |
| `extensions.htmlaboutaddons.recommendations.enabled` | false | Locked | No recommended add-ons in the `about:addons` lists | all.js |
| `extensions.getAddons.cache.enabled` | false | Locked | Shibi, 2026-11-12. No daily request that sends the IDs of installed add-ons to `services.addons.mozilla.org`; the existing cache is cleared. Add-on updates still work: they ask `versioncheck-bg.addons.mozilla.org`, not this cache, and the add-on blocklist comes from Remote Settings. Effect in `about:addons`: no AMO rating, review count, AMO description, screenshots, AMO icons or AMO listing link; add-ons show the name, description and icon from their own manifest | firefox.js |

### Mozilla promotions: locked off

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `signon.firefoxRelay.feature` | `""` | Locked | No Firefox Relay email-mask offers in login forms. `""` is not one of the values `LoginHelper` treats as available (`available`, `offered`, `enabled`, `disabled`), so Firefox treats the feature as not available. Relay needs a Mozilla account, which `identity.fxaccounts.enabled` (locked false) blocks anyway | firefox.js |
| `browser.contentblocking.report.monitor.enabled` | false | Locked | No Mozilla Monitor card in `about:protections` (already false in 160; locked) | firefox.js |
| `browser.vpn_promo.enabled` | false | Locked | No Mozilla VPN card in `about:protections` and no VPN promotions | firefox.js |
| `browser.contentblocking.report.show_mobile_app` | false | Locked | No Firefox mobile-app promotion in `about:protections` | firefox.js |
| `browser.uitour.enabled` | false | Locked | Mozilla web pages cannot drive UI tours of the browser | firefox.js |

### Prefetching: locked off

Found by the consent test (2026-11-12): a profile without uBlock Origin looked up `support.mozilla.org` at every
start, because Firefox resolves the hosts of links in its own pages ahead of use. These are the three prefs behind
the extension setting `privacy.network.networkPredictionEnabled` (`ext-privacy.js`), which uBlock Origin sets to
false by default ("Disable pre-fetching"); earlier runs, all with uBlock Origin, had them off already. Locked here
so that a profile without uBlock Origin behaves the same. **Side effect:** uBlock Origin's "Disable pre-fetching"
switch can no longer change them (Firefox reports the setting as not controllable by extensions); prefetching
stays off whatever that switch shows.

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `network.dns.disablePrefetch` | true | Locked | No DNS lookups for links before they are used | StaticPrefList.yaml |
| `network.prefetch-next` | false | Locked | No `<link rel=prefetch>` downloads | all.js |
| `network.http.speculative-parallel-limit` | 0 | Locked | No speculative connections (for example on hovering a link or typing in the address bar) | all.js |

### Network: region lookup locked off; checks off by default

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `browser.region.network.url` | `""` | Locked | No request to a location service to guess the user's country | all.js |
| `browser.region.update.enabled` | false | Locked | Same | all.js |
| `network.captive-portal-service.enabled` | false | Default | No check request to Mozilla at start and on network changes. Hotel or airport Wi-Fi login pages will not open by themselves; the user can turn it back on | StaticPrefList.yaml; firefox.js |
| `network.connectivity-service.enabled` | false | Default | No connectivity check request to Mozilla | all.js |

### Firefox accounts: locked off

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `identity.fxaccounts.enabled` | false | Locked | No Firefox accounts or sync. Set here instead of by the `DisableAccounts` policy, which also locks `about:welcome` off (see "Policies") | firefox.js |

### First run: uBlock Origin consent screen

Shibi's decision (2026-11-12), Store policy 10.1.5 ("with user consent and after initial download of the primary
product"): uBlock Origin is installed only if the user agrees at first run, as on Orbis for Android.

How it works, with no patch: Firefox 160's onboarding page `about:welcome` shows the screens in
`browser.aboutwelcome.screens` instead of Mozilla's own. The page and its screens are local; with Nimbus off (the
`DisableFirefoxStudies` and `DisableRemoteImprovements` policies, `nimbus.rollouts.enabled`, `UserMessaging`
`FirefoxLabs` false) Firefox reads the screens from that pref (the Nimbus feature's `fallbackPref`), and no
experiment can replace them. Firefox opens `about:welcome` once, in the first window of a new profile
(`OVERRIDE_NEW_PROFILE` in `BrowserContentHandler.sys.mjs`), so the question is never asked twice.

The screens (`ORBIS_UBO_CONSENT_SCREENS` in `orbis.cfg`; text from Android's `ubo_onboarding_title`,
`ubo_disclosure`, `ubo_etp_stays_on`, `ubo_continue` and `ubo_installing`):

1. "Block ads and trackers?", the disclosure (uBlock Origin is a separate GPL-3.0 project, not made or endorsed
   by Orbis or Mozilla, not included in Orbis; Orbis contacts addons.mozilla.org to download and update it; uBlock
   Origin downloads its own filter lists; Orbis chooses those lists at every start), one checkbox **"Install
   uBlock Origin ad blocker", on by default**, and a **Continue** button. Unchecked, the screen says "uBlock Origin
   will not be installed. Strict tracking protection stays on. You can install uBlock Origin later: open Add-ons
   and themes and search for uBlock Origin."
2. Checkbox on: Continue records `accepted`, starts the download from addons.mozilla.org
   (`INSTALL_ADDON_FROM_URL`, the same AMO URL the policy used) and shows "Installing uBlock Origin...". Firefox
   then shows its own "Add uBlock Origin?" prompt with the add-on's permissions; "Add" installs it. "Start
   browsing" opens the home page. Leaving `about:welcome` while that prompt is still open cancels the install
   (Firefox removes the prompt on navigation); moving to the second screen does not, which is why there is one.
3. Checkbox off: Continue records `declined` and opens the home page. Nothing is downloaded.

Later installs: Add-ons and themes (`about:addons`) search, or addons.mozilla.org. `ExtensionSettings` allows
uBlock Origin and keeps it working in private windows, and the `3rdparty` lists apply to any install.

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `browser.aboutwelcome.enabled` | true | Locked | `about:welcome` hosts the consent screen. The policies that would lock it false (`DisableAccounts`, `DisableFirefoxAccounts`, `OverrideFirstRunPage`, `UserMessaging` `SkipOnboarding`) are not used; `check-settings.py` fails if one comes back | firefox.js |
| `browser.aboutwelcome.screens` | `JSON.stringify(ORBIS_UBO_CONSENT_SCREENS)` (the two screens above) | Locked | Replaces Mozilla's onboarding screens (import, default browser, pinning, sign-in) with Orbis's consent screens. `check-settings.py` reads the screens and fails unless the only install action is uBlock Origin's AMO URL in the checked action of a checkbox that is on by default, collected by Continue, with a second screen after it | firefox.js |
| `browser.aboutwelcome.experimentsGate.enabled` | false | Locked | No splash screen that waits up to 8 seconds for Nimbus experiments before the first screen. Nimbus is off, so `AboutWelcomeParent` would skip the wait anyway; locked so that it never depends on that | firefox.js |
| `intl.multilingual.aboutWelcome.languageMismatchEnabled` | false | Locked | true in release builds. When the Windows language differs from Orbis's (en-US), `about:welcome` would negotiate a language pack and ask `services.addons.mozilla.org/api/v4/addons/language-tools/` before the user answers, on the decline path too (`AboutWelcomeChild.getAWContent`, `useLanguageSwitcher`). Orbis is English only (Fable's review of PR #9) | firefox.js (`#if defined(RELEASE_OR_BETA)`, both branches) |
| `trailhead.firstrun.didHandleCampaignAction` | true | Locked | Marks the install's campaign action as already handled. Otherwise `about:welcome` runs the action named by the install's attribution (for an MSIX, the Store campaign ID; for example pin to taskbar or set as default) when the first screen shows, before the user answers | code: browser/components/aboutwelcome/actors/AboutWelcomeParent.sys.mjs |
| `startup.homepage_welcome_url` | `"about:welcome"` | Locked | First-run page of a new profile: the consent screen. The branding (`firefox-branding.js`) sets `""`; this overrides it | code: browser/components/BrowserContentHandler.sys.mjs |
| `startup.homepage_welcome_url.additional` | `""` | Locked | No second first-run tab | code: browser/components/BrowserContentHandler.sys.mjs |
| `messaging-system-action.orbis.ubo.consent` | `"accepted"` or `"declined"` | Written once by the screen; not set by `orbis.cfg` | Records the answer on the screen (for checks and support). **It is not proof that uBlock Origin is installed:** after `accepted` the user can still refuse Firefox's prompt or leave the page before it, the download can fail, and the user can install or remove uBlock Origin later. Ask the Add-ons Manager for the install state. The screen asks for `orbis.ubo.consent`; Firefox's `SET_PREF` action adds the `messaging-system-action.` prefix to every pref outside its allow-list. Not set if the user closes the tab without answering; the screen is not shown again either way | Orbis's own pref |

`check-settings.py` also checks the pinned source for everything the screens use (the checkbox actions,
`collectSelect`, `INSTALL_ADDON_FROM_URL`, `OPEN_ABOUT_PAGE` with `home`, the two switches above), and that no
policy Orbis uses sets `browser.aboutwelcome.enabled`: a Firefox that ignores the screens shows Mozilla's full
onboarding instead. `docs/UPDATING.md` makes the `verify-build.py consent` test a required gate on every Firefox
update.

Not checked yet: the screen in a real window (the tests run headless, see `docs/BUILD.md`), and keyboard and
screen-reader use of the checkbox.

Follow-up to check: ASRouter's `cfr` and `message-groups` message providers are still enabled
(`browser.newtabpage.activity-stream.asrouter.providers.*`). `UserMessaging` turns off the recommendations they
show, but whether either can still fetch or show anything has not been checked.

### Tracking protection: Strict on first start, then the user's choice

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `browser.contentblocking.category` | `"strict"`, set once per profile | Default | ETP Strict as on Android. The `EnableTrackingProtection` policy is not used because it locks the category whenever it sets one. Firefox applies a category only when the pref has a user value, so `orbis.cfg` sets that value on the first start of a profile and then leaves it alone | code: browser-siteProtections.js |
| `orbis.privacy.etpStrictApplied` | true | Orbis's own | Records that the first-start value was set, so a user who later picks Standard keeps it | Orbis's own pref |

### AutoConfig loader (`defaults/pref/autoconfig.js`)

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `general.config.filename` | `"orbis.cfg"` | Default (in the install folder, read-only in the MSIX) | Loads `orbis.cfg` | code: read by `extensions/pref/autoconfig` |
| `general.config.obscure_value` | 0 | Default | `orbis.cfg` is plain text, so anyone can read it | all.js |

`orbis.cfg` runs in AutoConfig's sandbox, which Firefox turns on for the release update channel; it uses only the
pref functions. The loader does not change `general.config.sandbox_enabled`.

## Not changed on purpose

- Windows SmartScreen and the "downloaded from the internet" mark on files (owner decision).
- Search suggestions: the Firefox default (on, off in private windows) matches Android.
- Add-on signing, sandbox, process and JIT settings: never changed (AGENTS.md).
- Remote Settings, OCSP and the other calls in the next section.

## Network calls that remain

What Orbis still sends with these settings, read from the Firefox 160 source (Fable's review, 2026-11-12). Every row
goes into the privacy policy. The full network audit is PR 8.

First wire check (first Orbis build, 2026-11-12; `scripts/verify-build.py idle`, see `docs/BUILD.md`): a new
profile started headless and sampled for 3 minutes. Its DNS log (`MOZ_LOG=nsHostResolver:5`) covers only the
first 30 seconds (14:24:31 to 14:25:01 UTC): the release build's fast shutdown dropped the rest of the buffered
log. For the whole 3 minutes there is only TCP sampling every 4 seconds (`f-tcp.json`: 10 remote IP addresses on
port 443, not matched to host names). In those 30 seconds the DNS log has only hosts in this table: `firefox.settings.services.mozilla.com`, `firefox-settings-attachments.cdn.mozilla.net`,
`content-signature-2.cdn.mozilla.net`, `push.services.mozilla.com`, `aus5.mozilla.org`, `ciscobinary.openh264.org`,
`addons.mozilla.org`, `versioncheck-bg.addons.mozilla.org`, `publicsuffix.org`, `ublockorigin.github.io`,
`ublockorigin.pages.dev`, `cdn.jsdelivr.net`, `secure.fanboy.co.nz`, `malware-filter.gitlab.io` and `pgl.yoyo.org`.
What happened after the first 30 seconds is not known yet: the next build re-runs the check with
`MOZ_LOG=timestamp,sync,nsHostResolver:5`, which writes each line unbuffered.

Already off (above): telemetry, Normandy, Nimbus, DAP, crash reports; region lookup; captive-portal and connectivity
checks; Mozilla's DoH rollout; sponsored content and Contile; Google Safe Browsing and Widevine via Google; system
add-on updates; MITM priming; add-on recommendations; the AMO metadata cache.

| Call | Host | When | Why it stays |
|---|---|---|---|
| Remote Settings | `firefox.settings.services.mozilla.com`; attachments from `firefox-settings-attachments.cdn.mozilla.net` | At start and on push notifications | Security data: certificate revocation (CRLite), the add-on blocklist, tracking-protection lists, and more. Turning it off weakens security. Keep and disclose |
| Remote Settings signature certificate | `content-signature-2.cdn.mozilla.net` | When Remote Settings checks the signature of downloaded data, and again when the certificate chain changes or expires | Every Remote Settings collection is signed. Firefox downloads the signer's certificate chain (the `x5u` URL in the collection's metadata) to verify the signature, and rejects data whose signature does not verify. Without it Remote Settings data (CRLite, the add-on blocklist, tracking-protection lists) could not be trusted. Keep and disclose |
| Push websocket | `wss://push.services.mozilla.com` (`dom.push.serverURL`) | Opened at every start and kept open | Remote Settings uses it to learn of new data at once (broadcast), and websites use it for Web Push notifications. The connection carries a per-profile ID (UAID) that lets Mozilla's push server recognise the same profile across starts, and Mozilla sees the IP address. **On by Shibi's decision (2026-11-12)**: turning it off (`dom.push.enabled`) would delay security data to Remote Settings' periodic poll and break site notifications. Disclose in the privacy policy |
| GMP manifest and OpenH264 | `aus5.mozilla.org` (manifest); `ciscobinary.openh264.org` (OpenH264 download) | Manifest about once a day; OpenH264 once and on its updates | OpenH264 is the video codec WebRTC calls need. The manifest also lists Widevine, which is downloaded only if the user turns DRM on. Keep and disclose |
| Add-on updates and the uBlock Origin install | `addons.mozilla.org`, `versioncheck-bg.addons.mozilla.org` | uBlock Origin download only after the user agrees on the first-run screen (or installs it later); update checks about once a day | uBlock Origin is installed from AMO, not bundled (GPL-3.0), and must stay current. Unavoidable while add-ons are installed from AMO. Consent test (`verify-build.py consent`, 2026-11-12): no `addons.mozilla.org` lookup before the answer, and none at all in 60 seconds after "declined" |
| DNS prefetch of help links | `support.mozilla.org` (DNS lookup only) | **No longer**: was at start in a profile without uBlock Origin | Found by the consent test (2026-11-12) and stopped by locking prefetching off (see "Prefetching: locked off"). Listed so that the host is recognised if it comes back |
| uBlock Origin filter lists | `ublockorigin.github.io`, `ublockorigin.pages.dev`, `cdn.jsdelivr.net`, `secure.fanboy.co.nz`, `raw.githubusercontent.com`, `malware-filter.gitlab.io`, `curbengh.github.io`, `phishing-filter.pages.dev`, `pgl.yoyo.org` | Only with uBlock Origin installed: right after the install, then on uBlock Origin's own update schedule (several days per list) | The lists are the malware, phishing, tracker and cookie-notice protection. Requests from uBlock Origin, not from Firefox. uBlock Origin lists several mirrors per list and picks one per download, so the hosts vary between runs. `raw.githubusercontent.com` is the `contentURL` of uBlock Origin's list catalogue, `assets.json`, which uBlock Origin updates like a list (its `cdnURLs`, `ublockorigin.github.io`, `ublockorigin.pages.dev` and `cdn.jsdelivr.net`, are tried too); `curbengh.github.io` and `phishing-filter.pages.dev` were not seen in the first idle run but are contacted on list updates: in uBlock Origin's `assets.json` they are mirrors (`cdnURLs`), next to `malware-filter.gitlab.io`, of "Phishing URL Blocklist" (`curben-phishing`: both hosts) and "Online Malicious URL Blocklist" (`urlhaus-1`: `curbengh.github.io`) |
| Public suffix list | `publicsuffix.org` | Only with uBlock Origin installed: after the install, then on uBlock Origin's update schedule | Requested by uBlock Origin (`public_suffix_list.dat` in its `assets.json`), which needs the current public suffix list to tell which part of a host name is the site (`example.co.uk`), for first-party and third-party rules. uBlock Origin ships a copy and updates it from `publicsuffix.org`. Keep and disclose |
| OCSP | The certificate authority's OCSP responder | When a site's certificate needs a revocation check that CRLite (`security.pki.crlite_mode` 2, data from Remote Settings) cannot answer on the device | Certificate revocation checking (`security.OCSP.enabled` 1). It tells the CA which site's certificate is checked. Keep |
| Search suggestions | `duckduckgo.com` | While the user types in the address bar (not in private windows) | Firefox default, same as Android. The user can turn suggestions off. Disclose |
| Translation models | Remote Settings attachments (Mozilla's CDN) | Only when the user translates a page into a new language pair | Translation runs on the device; the model is downloaded once. Disclose |
| Geolocation | Windows location service | Only when a site asks and the user allows | On Windows Firefox uses the system provider, not Google's geolocation API (`geo.provider.network.url` is not set on Windows) |
