// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.

// Orbis: AutoConfig loader. Goes to <install folder>\defaults\pref\autoconfig.js and tells Firefox to read
// <install folder>\orbis.cfg at startup. orbis.cfg is plain text (obscure_value 0). Do not set
// general.config.sandbox_enabled: on the release update channel orbis.cfg runs sandboxed, which only allows
// the pref functions, and that is all it needs. scripts/check-settings.py checks these three rules.
pref("general.config.filename", "orbis.cfg");
pref("general.config.obscure_value", 0);
