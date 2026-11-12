/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

// This file contains branding-specific prefs. The file name is fixed by
// browser/branding/branding-common.mozbuild.
//
// Orbis: no Mozilla start, welcome or update pages. The update prefs of the
// unofficial template are dropped: Orbis builds no updater (the Microsoft Store
// updates it). The template's devtools.selfxss.count = 5 is dropped too, so the
// console keeps Firefox's paste warning against self-XSS scams.

pref("startup.homepage_override_url", "");
pref("startup.homepage_welcome_url", "");
pref("startup.homepage_welcome_url.additional", "");
