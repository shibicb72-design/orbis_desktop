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
| Captive-portal and connectivity checks | Off, user can turn them on |
| `about:config` | Open (no policy blocks it) |

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
| `DisableDefaultBrowserAgent` | `true` | Locked | No background agent. Also not built (PR 4) |
| `DontCheckDefaultBrowser` | `true` | Locked | No "make default" prompt at every start; the user can still make Orbis the default in Settings |
| `DisableFeedbackCommands` | `true` | Locked | Removes "Report deceptive site" (goes to Google) and "Submit feedback" (Mozilla) |
| `SkipTermsOfUse` | `true` | Locked | Mozilla's Terms of Use prompt does not apply to Orbis |
| `OverrideFirstRunPage` | `""` | Locked | No Mozilla welcome page or onboarding. An Orbis first-run page comes later (PR 9) |
| `OverridePostUpdatePage` | `""` | Locked | No Mozilla "what's new" page after updates |
| `NoDefaultBookmarks` | `true` | Locked | Firefox's default bookmarks point at Mozilla sites |
| `FirefoxHome` | `SponsoredTopSites`, `Stories`, `SponsoredStories`, `Weather` false; `Locked` | Locked | No sponsored or recommended content on the new-tab page; stories and weather come from Mozilla's servers |
| `FirefoxSuggest` | `WebSuggestions`, `SponsoredSuggestions`, `ImproveSuggest`, `OnlineEnabled` false; `Locked` | Locked | No sponsored or Mozilla-served suggestions in the address bar |
| `UserMessaging` | `ExtensionRecommendations`, `FeatureRecommendations`, `UrlbarInterventions`, `MoreFromMozilla`, `FirefoxLabs` false; `SkipOnboarding` true; `Locked` | Locked | No Mozilla marketing messages. Firefox Labs is opt-in Nimbus experiments |
| `AIControls` | `Default` blocked and locked; `Translations` available, not locked | AI features locked off; translation is a default | No AI chatbot (locked). The same `Default` also blocks link-preview key points, smart tab groups, smart window, PDF alt text and speech recognition. Translation runs on the device; its models download from Mozilla (to disclose in the privacy policy) |
| `HttpsOnlyMode` | `"enabled"` | Default | HTTPS-only in normal and private windows, as on Android. The user can turn it off or add exceptions |
| `EncryptedMediaExtensions` | `Enabled` false | Default | DRM is a closed Google component downloaded on demand. Netflix and similar sites will not play until the user enables it |
| `DNSOverHTTPS` | `Enabled` false | Default | No third-party DNS resolver by default. Sets `network.trr.mode` to 5 ("off by choice"), which also stops Mozilla's regional DoH rollout. The user can turn DoH on |
| `SearchEngines` | `Default` DuckDuckGo; `Add` Brave Search and Startpage | Default | Same default and engines as Android. The added engines have no icon URL (so no request to fetch one) and no suggestion URL (so no search suggestions from them). Where Firefox already ships Startpage (regions at, ch, de, fr, nl) the added copy has a duplicate name; Firefox logs an error and keeps its own |
| `ExtensionSettings` | `*`: allowed types extension, theme, dictionary, sitepermission. `uBlock0@raymondhill.net`: `normal_installed` from addons.mozilla.org, `private_browsing` true | Language packs blocked; uBlock Origin cannot be removed but can be disabled | English only (no `locale` type). uBlock Origin installs automatically on first run and works in private windows; the user can switch it off on a broken site. It is downloaded from AMO, not bundled (GPL-3.0) |
| `3rdparty` | uBlock Origin `toOverwrite.filterLists`: `user-filters`, `ublock-filters`, `ublock-badware`, `ublock-privacy`, `ublock-unbreak`, `ublock-quick-fixes`, `easylist`, `easyprivacy`, `urlhaus-1`, `plowe-0`, `curben-phishing` | Re-applied at every start | uBlock Origin's own defaults plus "Phishing URL Blocklist" (`curben-phishing`), which stands in for Google Safe Browsing's phishing protection. Malware: `urlhaus-1` and `ublock-badware`. uBlock Origin applies `toOverwrite` at every launch, so a user's list changes last only until the next start |

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
- Remote Settings (certificate revocation, add-on blocklist, tracking-protection lists): security data from Mozilla;
  kept, and to be disclosed in the privacy policy.
- System add-on updates and the media-plugin service (OpenH264, Widevine) still contact Mozilla's update server.
  Whether the Widevine download is skipped while DRM is off is unverified. To review in the network audit (PR 8).
