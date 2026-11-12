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

## Defaults pending Shibi's OK

Shibi decided (2026-11-12): Microsoft Store only, release channel, no Google Safe Browsing, uBlock Origin installed
automatically with its "Phishing URL Blocklist" on, no servers, accounts, sync, analytics, telemetry or studies,
English only. The rows below follow Fable's recommended defaults and wait for Shibi's OK:

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

Three more defaults also wait for Shibi's decision; they are described in "Network calls that remain" below:

| Choice | Orbis default now |
|---|---|
| uBlock Origin filter lists | Overwritten with Orbis's list set at every launch (`3rdparty` `toOverwrite`) |
| Push websocket (`push.services.mozilla.com`) | On (Firefox default) |
| AMO metadata cache (`extensions.getAddons.cache.enabled`) | On (Firefox default) |

## Differences from Orbis for Android

Read from `work-orbis` (`engine/GeckoEngineImpl.kt`, `settings/BrowserSettings.kt`, `engine/SearchEngine.kt`).

| Area | Android | Desktop | Why |
|---|---|---|---|
| Google Safe Browsing | On (`ContentBlocking.SafeBrowsing.DEFAULT`) | Off, Google endpoints blanked | Owner decision 2026-11-12 |
| `about:config` | Blocked (`aboutConfigEnabled(false)`) | Open | Desktop convention; locked prefs stay locked there. Pending OK |
| Tracking-protection level | Strict, fixed; per-site exceptions only | Strict on first start; the user may switch to Standard or Custom | "Adjustable" ETP. Pending OK |
| uBlock Origin | From AMO after the user agrees; uBlock Origin's default lists | Installed automatically by policy; default lists plus "Phishing URL Blocklist" | Owner decision 2026-11-12 |
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
| `DisableAccounts` | `true` | Locked | No Firefox accounts or sync. Locks `identity.fxaccounts.enabled` to false. `DisableFirefoxAccounts` is not set: Firefox ignores it when `DisableAccounts` is present |
| `IPProtectionAvailable` | `false` | Locked | The built-in VPN needs a Mozilla account and Mozilla's servers |
| `DisableAppUpdate` | `true` | Locked | The Microsoft Store updates Orbis. The updater is also not built (PR 4) |
| `DisableSystemAddonUpdate` | `true` | Locked | `DisableAppUpdate` does not cover system add-ons: with `extensions.systemAddon.update.enabled` (true in firefox.js) Firefox polls `aus5.mozilla.org` for new system add-ons outside the Store. The policy disallows the `SysAddonUpdate` feature, which `AddonManager.systemUpdateEnabled` checks. The built-in system add-ons ship in the package and update with it |
| `DisableDefaultBrowserAgent` | `true` | Locked | No background agent. Also not built (PR 4) |
| `DontCheckDefaultBrowser` | `true` | Locked | No "make default" prompt at every start; the user can still make Orbis the default in Settings |
| `DisableFeedbackCommands` | `true` | Locked | Removes "Report deceptive site" (goes to Google) and "Submit feedback" (Mozilla) |
| `SkipTermsOfUse` | `true` | Locked | Mozilla's Terms of Use prompt does not apply to Orbis |
| `OverrideFirstRunPage` | `""` | Locked | No Mozilla welcome page or onboarding. An Orbis first-run page comes later (PR 9) |
| `OverridePostUpdatePage` | `""` | Locked | No Mozilla "what's new" page after updates |
| `NoDefaultBookmarks` | `true` | Locked | Firefox's default bookmarks point at Mozilla sites |
| `FirefoxHome` | `SponsoredTopSites`, `Stories`, `SponsoredStories`, `Weather` false; `Locked` | Locked | No sponsored or recommended content on the new-tab page; stories and weather come from Mozilla's servers |
| `FirefoxSuggest` | `WebSuggestions`, `SponsoredSuggestions`, `ImproveSuggest`, `OnlineEnabled` false; `Locked` | Locked | No sponsored or Mozilla-served suggestions in the address bar |
| `UserMessaging` | `ExtensionRecommendations`, `FeatureRecommendations`, `UrlbarInterventions`, `MoreFromMozilla`, `FirefoxLabs` false; `SkipOnboarding` true; `Locked` | Locked | No Mozilla marketing messages. Firefox Labs is opt-in Nimbus experiments. Side effect: `FeatureRecommendations` false with `Locked` also sets and locks `browser.translations.mostRecentTargetLanguages` to the user's first web language, so the translation panel skips its intro and its "recent languages" list stays fixed to that language |
| `AIControls` | `Default` blocked and locked; `Translations` available, not locked | AI features locked off; translation is a default | No AI chatbot (locked). The same `Default` also blocks link-preview key points, smart tab groups, smart window, PDF alt text and speech recognition. Translation runs on the device; its models download from Mozilla (to disclose in the privacy policy) |
| `HttpsOnlyMode` | `"enabled"` | Default | HTTPS-only in normal and private windows, as on Android. The user can turn it off or add exceptions |
| `EncryptedMediaExtensions` | `Enabled` false | Default | DRM is a closed Google component downloaded on demand. Netflix and similar sites will not play until the user enables it |
| `DNSOverHTTPS` | `Enabled` false | Default | No third-party DNS resolver by default. Sets `network.trr.mode` to 5 ("off by choice"), which also stops Mozilla's regional DoH rollout. The user can turn DoH on |
| `SearchEngines` | `Default` DuckDuckGo; `Add` Brave Search and Startpage | Default | Same default and engines as Android. The added engines have no icon URL (so no request to fetch one) and no suggestion URL (so no search suggestions from them) |
| `ExtensionSettings` | `*`: allowed types extension, theme, dictionary, sitepermission. `uBlock0@raymondhill.net`: `normal_installed` from addons.mozilla.org, `private_browsing` true | Language packs blocked; uBlock Origin cannot be removed but can be disabled | English only (no `locale` type). uBlock Origin installs automatically on first run and works in private windows; the user can switch it off on a broken site. It is downloaded from AMO, not bundled (GPL-3.0) |
| `3rdparty` | uBlock Origin `toOverwrite.filterLists`: `user-filters`, `ublock-filters`, `ublock-badware`, `ublock-privacy`, `ublock-unbreak`, `ublock-quick-fixes`, `easylist`, `easyprivacy`, `urlhaus-1`, `plowe-0`, `curben-phishing`, `fanboy-cookiemonster`, `ublock-cookies-easylist` | Re-applied at every start (pending Shibi) | uBlock Origin's own defaults plus "Phishing URL Blocklist" (`curben-phishing`), which stands in for Google Safe Browsing's phishing protection. Malware: `urlhaus-1` and `ublock-badware`. Cookie notices (plan C.2): uBlock Origin's "EasyList/uBO – Cookie Notices" pair, `fanboy-cookiemonster` and `ublock-cookies-easylist`, both off by default in uBlock Origin; the AdGuard pair is not added, to avoid double filtering. These lists hide or block notices; they do not click "accept" or "reject". uBlock Origin applies `toOverwrite` at every launch, so a user's list changes last only until the next start |

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
| `extensions.getAddons.showPane` | false | Locked | No "Recommendations" pane in `about:addons` (content from addons.mozilla.org) | code: toolkit/mozapps/extensions/content/aboutaddons-utils.mjs |
| `extensions.htmlaboutaddons.recommendations.enabled` | false | Locked | No recommended add-ons in the `about:addons` lists | all.js |

### Mozilla promotions: locked off

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `signon.firefoxRelay.feature` | `""` | Locked | No Firefox Relay email-mask offers in login forms. `""` is not one of the values `LoginHelper` treats as available (`available`, `offered`, `enabled`, `disabled`), so Firefox treats the feature as not available. Relay needs a Mozilla account, which `DisableAccounts` blocks anyway | firefox.js |
| `browser.contentblocking.report.monitor.enabled` | false | Locked | No Mozilla Monitor card in `about:protections` (already false in 160; locked) | firefox.js |
| `browser.vpn_promo.enabled` | false | Locked | No Mozilla VPN card in `about:protections` and no VPN promotions | firefox.js |
| `browser.contentblocking.report.show_mobile_app` | false | Locked | No Firefox mobile-app promotion in `about:protections` | firefox.js |
| `browser.uitour.enabled` | false | Locked | Mozilla web pages cannot drive UI tours of the browser | firefox.js |

### Network: region lookup locked off; checks off by default

| Pref | Value | Locked? | Reason | Source |
|---|---|---|---|---|
| `browser.region.network.url` | `""` | Locked | No request to a location service to guess the user's country | all.js |
| `browser.region.update.enabled` | false | Locked | Same | all.js |
| `network.captive-portal-service.enabled` | false | Default | No check request to Mozilla at start and on network changes. Hotel or airport Wi-Fi login pages will not open by themselves; the user can turn it back on | StaticPrefList.yaml; firefox.js |
| `network.connectivity-service.enabled` | false | Default | No connectivity check request to Mozilla | all.js |

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

What Orbis still sends with these settings, read from the Firefox 160 source (Fable's review, 2026-11-12). Nothing
here was captured on the wire yet; the network audit (PR 8) confirms it. Every row goes into the privacy policy.

Already off (above): telemetry, Normandy, Nimbus, DAP, crash reports; region lookup; captive-portal and connectivity
checks; Mozilla's DoH rollout; sponsored content and Contile; Google Safe Browsing and Widevine via Google; system
add-on updates; MITM priming; add-on recommendations.

| Call | Host | When | Why it stays |
|---|---|---|---|
| Remote Settings | `firefox.settings.services.mozilla.com` (attachments from Mozilla's CDN) | At start and on push notifications | Security data: certificate revocation (CRLite), the add-on blocklist, tracking-protection lists, and more. Turning it off weakens security. Keep and disclose |
| Push websocket | `wss://push.services.mozilla.com` (`dom.push.serverURL`) | Opened at every start and kept open | Remote Settings uses it to learn of new data at once (broadcast), and websites use it for Web Push notifications. It carries a per-profile ID. **Pending Shibi**: keep (default) or turn off, which delays Remote Settings to its periodic poll and breaks site notifications |
| GMP manifest and OpenH264 | `aus5.mozilla.org` (manifest); `ciscobinary.openh264.org` (OpenH264 download) | Manifest about once a day; OpenH264 once and on its updates | OpenH264 is the video codec WebRTC calls need. The manifest also lists Widevine, which is downloaded only if the user turns DRM on. Keep and disclose |
| Add-on updates and the uBlock Origin install | `addons.mozilla.org`, `versioncheck-bg.addons.mozilla.org` | uBlock Origin download on first start; update checks about once a day | uBlock Origin is installed from AMO, not bundled (GPL-3.0), and must stay current. Unavoidable while add-ons are installed from AMO |
| uBlock Origin filter lists | `ublockorigin.github.io`, `ublockorigin.pages.dev`, `cdn.jsdelivr.net`, `easylist`/`fanboy` hosts, `malware-filter.gitlab.io`, `curbengh.github.io`, `phishing-filter.pages.dev`, `pgl.yoyo.org` | uBlock Origin's own update schedule (several days per list) | The lists are the malware, phishing, tracker and cookie-notice protection. Requests from uBlock Origin, not from Firefox |
| AMO metadata cache | `services.addons.mozilla.org` (`extensions.getAddons.get.url`) | About once a day | Fetches names, icons and descriptions for installed add-ons; sends their IDs. Optional. **Pending Shibi**: keep (default) or set `extensions.getAddons.cache.enabled` false |
| OCSP | The certificate authority's OCSP responder | When a site's certificate needs a revocation check that CRLite (`security.pki.crlite_mode` 2, data from Remote Settings) cannot answer on the device | Certificate revocation checking (`security.OCSP.enabled` 1). It tells the CA which site's certificate is checked. Keep |
| Search suggestions | `duckduckgo.com` | While the user types in the address bar (not in private windows) | Firefox default, same as Android. The user can turn suggestions off. Disclose |
| Translation models | Remote Settings attachments (Mozilla's CDN) | Only when the user translates a page into a new language pair | Translation runs on the device; the model is downloaded once. Disclose |
| Geolocation | Windows location service | Only when a site asks and the user allows | On Windows Firefox uses the system provider, not Google's geolocation API (`geo.provider.network.url` is not set on Windows) |
