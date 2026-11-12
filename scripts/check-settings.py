# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Static check of the Orbis privacy layer against the pinned Firefox source.

Run it isolated, so nothing from the current folder or the Firefox tree is imported:

    python -I scripts/check-settings.py [--source DIR] [--overlay DIR] [--ubo-assets FILE]

--source is a Firefox checkout (default %USERPROFILE%\\orbis_desktop_src\\firefox), or any folder that
holds these four files at their usual relative paths:

    modules/libpref/init/StaticPrefList.yaml
    modules/libpref/init/all.js
    browser/app/profile/firefox.js
    browser/components/enterprisepolicies/schemas/policies-schema.json

What fails (exit code 1):

- a pref in orbis.cfg or autoconfig.js that Firefox does not know. A pref is known when one of the three
  pref files defines it. With a full checkout, a pref that no pref file defines but that Firefox code reads
  by name is accepted and reported as "code"; review those by hand. Prefs named "orbis.*" are Orbis's own
  and are reported, not checked.
- a value whose type differs from the pref's type in the pref files (bool, int, string);
- a pref set twice in orbis.cfg by lockPref or defaultPref;
- policies.json: a policy name the schema does not have, or any value the schema rejects (unknown keys,
  wrong types, values outside the allowed list), or a policy or key that the schema marks as added after,
  or removed in, the Firefox version of the source;
- the AutoConfig loader not pointing at orbis.cfg, being obscured, or switching the sandbox off;
- a pref or top-level policy with no row (its name in backticks) in docs/SETTINGS.md;
- with --ubo-assets (uBlock Origin's assets.json): a filter-list token that uBlock Origin does not know,
  or one of uBlock Origin's default lists missing from our toOverwrite.filterLists.
- uBlock Origin consent (Store policy 10.1.5): any add-on that policies.json installs without the user
  (ExtensionSettings force_installed or normal_installed, Extensions.Install); a policy that switches
  about:welcome off (OverrideFirstRunPage, DisableAccounts, DisableFirefoxAccounts, UserMessaging
  SkipOnboarding); orbis.cfg not locking about:welcome on as the first-run page with
  ORBIS_UBO_CONSENT_SCREENS; and in those screens: not exactly one INSTALL_ADDON_FROM_URL, or that one not
  the uBlock Origin AMO URL in the checkedAction of a checkbox that is on by default, or the Continue button
  not collecting the checkbox, or no screen after it (leaving about:welcome cancels an install whose
  permission prompt is still open); orbis.cfg not locking the language-mismatch step, the campaign action,
  the Nimbus wait and the additional welcome page off (CONSENT_LOCKS). With a full checkout also: the
  pinned source missing anything the screens use (CONSENT_SOURCE, about:home in ALLOWED_ABOUT_PAGES), or a
  policy in policies.json that sets browser.aboutwelcome.enabled in Policies.sys.mjs.

Prints OK, or every problem found. Reads files only; changes nothing.
"""

import argparse
import json
import os
import re
import subprocess
import sys

PREF_FILES = (
    "modules/libpref/init/StaticPrefList.yaml",
    "modules/libpref/init/all.js",
    "browser/app/profile/firefox.js",
)
SCHEMA_FILE = "browser/components/enterprisepolicies/schemas/policies-schema.json"
VERSION_FILE = "browser/config/version.txt"
UBO_ID = "uBlock0@raymondhill.net"
UBO_AMO_URL = "https://addons.mozilla.org/firefox/downloads/latest/uBlock0@raymondhill.net/latest.xpi"
CONSENT_VAR = "ORBIS_UBO_CONSENT_SCREENS"
SILENT_INSTALL_MODES = ("force_installed", "normal_installed")
# Policies that lock browser.aboutwelcome.enabled to false (Policies.sys.mjs), which removes the consent screen.
# With a full checkout, check_consent_source() also finds any other policy that touches that pref.
WELCOME_OFF_POLICIES = ("OverrideFirstRunPage", "DisableAccounts", "DisableFirefoxAccounts")
# orbis.cfg locks the consent screen depends on (values as written in orbis.cfg).
CONSENT_LOCKS = (
    ("browser.aboutwelcome.enabled", "true"),
    ("startup.homepage_welcome_url", "\"about:welcome\""),
    ("startup.homepage_welcome_url.additional", "\"\""),
    ("browser.aboutwelcome.experimentsGate.enabled", "false"),
    # Otherwise about:welcome asks services.addons.mozilla.org for language packs before consent.
    ("intl.multilingual.aboutWelcome.languageMismatchEnabled", "false"),
    # Otherwise about:welcome runs the attribution (Store campaign) action before consent.
    ("trailhead.firstrun.didHandleCampaignAction", "true"),
)
# What the consent screen needs from the pinned source: (file, strings that must be in it). If Firefox drops or
# renames one, about:welcome may ignore Orbis's screens and show Mozilla's onboarding, or skip the consent logic.
CONSENT_SOURCE = (
    ("browser/components/aboutwelcome/content/aboutwelcome.bundle.js",
     ("checkedAction", "uncheckedAction", "uncheckedNotice", "collectSelect", "AWGetUnhandledCampaignAction")),
    ("toolkit/components/messaging-system/lib/SpecialMessageActions.sys.mjs",
     ('case "INSTALL_ADDON_FROM_URL"', 'case "OPEN_ABOUT_PAGE"', 'case "SET_PREF"', 'case "MULTI_ACTION"',
      "orderedExecution", "messaging-system-action.")),
    ("browser/components/aboutwelcome/actors/AboutWelcomeChild.sys.mjs",
     ("featureConfig.languageMismatchEnabled",)),
    ("browser/components/aboutwelcome/actors/AboutWelcomeParent.sys.mjs",
     ('"trailhead.firstrun.didHandleCampaignAction"',)),
    ("browser/components/BrowserContentHandler.sys.mjs",
     # Re-asking relies on: an empty saved milestone means a new profile, which opens the welcome page.
     ("return savedmstone ? OVERRIDE_NEW_MSTONE : OVERRIDE_NEW_PROFILE", '"startup.homepage_welcome_url"',
      '"browser.startup.homepage_override.mstone"')),
    ("browser/components/shell/ShellService.sys.mjs",
     # A repeated ask turns the first-run Start-menu pin off with this pref.
     ('"browser.shell.disableStartMenuPin"',)),
    ("toolkit/components/nimbus/FeatureManifest.yaml",
     ("fallbackPref: browser.aboutwelcome.screens",
      "fallbackPref: intl.multilingual.aboutWelcome.languageMismatchEnabled")),
)
SMA_FILE = "toolkit/components/messaging-system/lib/SpecialMessageActions.sys.mjs"
# Orbis's own prefs: "orbis.*", and the consent choice, which Firefox's SET_PREF stores under its own prefix.
OWN_PREFIXES = ("orbis.", "messaging-system-action.orbis.")
CONSENT_CHOICE_PREF = "orbis.ubo.consent"
MSTONE_PREF = "browser.startup.homepage_override.mstone"
POLICIES_CODE = "browser/components/enterprisepolicies/Policies.sys.mjs"

# Code search (full checkout only): folders that hold product code, and file types that read prefs.
CODE_DIRS = ("browser", "toolkit", "services", "netwerk", "modules", "dom", "security", "extensions",
             "widget", "xpcom", "docshell", "uriloader", "remote", "image", "layout", "gfx", "js/xpconnect")
CODE_EXTS = (".js", ".mjs", ".jsm", ".cpp", ".h", ".py", ".json", ".toml", ".yaml", ".rs", ".ts", ".html")
SKIP_DIR_NAMES = {"test", "tests", "testing", "mochitest", "xpcshell", "browser-test", "unit", "gtest",
                  "crashtests", "reftests", "fixtures", ".git", "node_modules"}

problems = []


def fail(msg):
    problems.append(msg)


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# --------------------------------------------------------------------------------------------------
# Pref definitions in the Firefox source
# --------------------------------------------------------------------------------------------------

def yaml_type(t):
    t = t.strip()
    if "Bool" in t or t == "bool":
        return "bool"
    if "Int" in t or "int" in t or "Uint" in t:
        return "int"
    if "String" in t:
        return "string"
    if "Float" in t or t == "float":
        return "float"
    return "unknown"


def literal_type(lit):
    lit = lit.strip()
    if lit in ("true", "false"):
        return "bool"
    if re.fullmatch(r"-?\d+", lit):
        return "int"
    if re.fullmatch(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", lit):
        return "string"
    return "expr"


def load_pref_defs(source):
    """name -> list of (file, type, condition)."""
    defs = {}

    path = os.path.join(source, PREF_FILES[0])
    conds = []
    name = None
    for line in read_text(path).splitlines():
        m = re.match(r"#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)", line)
        if m:
            kw, rest = m.group(1), m.group(2).strip()
            if kw in ("if", "ifdef", "ifndef"):
                conds.append("%s %s" % (kw, rest))
            elif kw in ("elif", "else") and conds:
                conds[-1] = conds[-1] + " / " + kw + (" " + rest if rest else "")
            elif kw == "endif" and conds:
                conds.pop()
            continue
        m = re.match(r"- name: (\S+)\s*$", line)
        if m:
            name = m.group(1)
            defs.setdefault(name, []).append([PREF_FILES[0], "unknown", " && ".join(conds)])
            continue
        m = re.match(r"\s+type: (\S+)", line)
        if m and name:
            defs[name][-1][1] = yaml_type(m.group(1))
            name = None

    for rel in PREF_FILES[1:]:
        conds = []
        for line in read_text(os.path.join(source, rel)).splitlines():
            m = re.match(r"#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)", line)
            if m:
                kw, rest = m.group(1), m.group(2).strip()
                if kw in ("if", "ifdef", "ifndef"):
                    conds.append("%s %s" % (kw, rest))
                elif kw in ("elif", "else") and conds:
                    conds[-1] = conds[-1] + " / " + kw + (" " + rest if rest else "")
                elif kw == "endif" and conds:
                    conds.pop()
                continue
            m = re.match(r"\s*(?:pref|sticky_pref|lockPref)\(\s*\"([^\"]+)\"\s*,\s*(.*?)\)\s*;", line)
            if m:
                defs.setdefault(m.group(1), []).append([rel, literal_type(m.group(2)), " && ".join(conds)])
    return defs


def search_code(source, names):
    """For a full checkout: name -> first file (relative) that quotes the pref name."""
    found = {}
    if not names:
        return found
    pattern = re.compile("[\"'](" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
                         + ")[\"']")
    for top in CODE_DIRS:
        root = os.path.join(source, top)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for fn in filenames:
                if not fn.endswith(CODE_EXTS) or "test" in fn.lower():
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except OSError:
                    continue
                for m in pattern.finditer(text):
                    n = m.group(1)
                    if n not in found:
                        found[n] = os.path.relpath(full, source).replace("\\", "/")
                if len(found) == len(names):
                    return found
    return found


# --------------------------------------------------------------------------------------------------
# Orbis files
# --------------------------------------------------------------------------------------------------

CALL_RE = re.compile(r"\b(lockPref|defaultPref|pref|clearPref|unlockPref|getPref)\(\s*\"([^\"]+)\"\s*(?:,\s*(.*?))?\)")


def strip_line_comment(line):
    """The line without a trailing // comment. A // inside a "..." or '...' string (for example
    "https://...") is part of the string, not a comment."""
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif line.startswith("//", i):
            return line[:i]
        i += 1
    return line


def parse_cfg_calls(path, skip_first_line):
    """List of (function, name, value literal or None, line number)."""
    calls = []
    lines = read_text(path).splitlines()
    for i, line in enumerate(lines, 1):
        if skip_first_line and i == 1:
            continue
        code = strip_line_comment(line)
        for m in CALL_RE.finditer(code):
            calls.append((m.group(1), m.group(2), m.group(3), i))
    return calls


# --------------------------------------------------------------------------------------------------
# Minimal JSON-schema validator for Firefox's policies-schema.json
# --------------------------------------------------------------------------------------------------

def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3]) or (0,)


def json_type_ok(value, t):
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "null":
        return value is None
    return True


class Validator:
    def __init__(self, schema, ff_version):
        self.schema = schema
        self.ff = version_tuple(ff_version)

    def resolve(self, s):
        while isinstance(s, dict) and "$ref" in s:
            ref = s["$ref"]
            if not ref.startswith("#/definitions/"):
                raise ValueError("unsupported $ref " + ref)
            merged = dict(self.schema["definitions"][ref[len("#/definitions/"):]])
            for k, v in s.items():
                if k != "$ref":
                    merged[k] = v
            s = merged
        return s

    def compat(self, s, where):
        c = s.get("x-compatibility", {}).get("firefox") if isinstance(s, dict) else None
        if not c:
            return
        added, removed = c.get("version_added"), c.get("version_removed")
        if added is False:
            fail("%s: the schema says this is not available in Firefox (release)" % where)
        elif added and version_tuple(added) > self.ff:
            fail("%s: added in Firefox %s, source is %s" % (where, added, ".".join(map(str, self.ff))))
        if removed and version_tuple(removed) <= self.ff:
            fail("%s: removed in Firefox %s" % (where, removed))

    def errors(self, value, s, where):
        """Returns a list of error strings (does not record them)."""
        s = self.resolve(s)
        errs = []
        t = s.get("type")
        if t is not None:
            types = t if isinstance(t, list) else [t]
            if not any(json_type_ok(value, x) for x in types):
                return ["%s: expected %s, got %s" % (where, "/".join(types), type(value).__name__)]
        if "const" in s and value != s["const"]:
            errs.append("%s: must be %r" % (where, s["const"]))
        if "enum" in s and value not in s["enum"]:
            errs.append("%s: %r is not one of %r" % (where, value, s["enum"]))
        if "oneOf" in s:
            ok = [b for b in s["oneOf"] if not self.errors(value, b, where)]
            if len(ok) != 1:
                allowed = [b.get("const") for b in s["oneOf"] if "const" in b]
                errs.append("%s: %r does not match exactly one allowed form%s" % (
                    where, value, (" " + repr(allowed)) if allowed else ""))
        if "anyOf" in s:
            if not any(not self.errors(value, b, where) for b in s["anyOf"]):
                errs.append("%s: %r matches none of the allowed forms" % (where, value))
        if isinstance(value, str):
            if "maxLength" in s and len(value) > s["maxLength"]:
                errs.append("%s: longer than %d" % (where, s["maxLength"]))
            if "pattern" in s and not re.search(s["pattern"], value):
                errs.append("%s: %r does not match %s" % (where, value, s["pattern"]))
            if s.get("format") == "moz-url" and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
                errs.append("%s: %r is not a URL" % (where, value))
        if isinstance(value, list) and "items" in s:
            for i, item in enumerate(value):
                errs += self.errors(item, s["items"], "%s[%d]" % (where, i))
        if isinstance(value, dict):
            props = s.get("properties", {})
            pats = s.get("patternProperties", {})
            for r in s.get("required", []):
                if r not in value:
                    errs.append("%s: missing required key %r" % (where, r))
            for k, v in value.items():
                sub = "%s.%s" % (where, k)
                if k in props:
                    self.compat(props[k], sub)
                    errs += self.errors(v, props[k], sub)
                    continue
                matched = [p for p in pats if re.search(p, k)]
                if matched:
                    for p in matched:
                        errs += self.errors(v, pats[p], sub)
                    continue
                add = s.get("additionalProperties")
                if isinstance(add, dict):
                    errs += self.errors(v, add, sub)
                elif add is not True and (props or pats):
                    errs.append("%s: unknown key (the schema has no such property)" % sub)
        return errs


# --------------------------------------------------------------------------------------------------
# uBlock Origin consent (Store policy 10.1.5)
# --------------------------------------------------------------------------------------------------

def find_installs(node, path="screens"):
    """Every (path, action) in node whose type is INSTALL_ADDON_FROM_URL."""
    found = []
    if isinstance(node, dict):
        if node.get("type") == "INSTALL_ADDON_FROM_URL":
            found.append((path, node))
        for k, v in node.items():
            found += find_installs(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found += find_installs(v, "%s[%d]" % (path, i))
    return found


def check_consent_source(source, full_checkout, policies):
    """Fails if the pinned source no longer has what the consent screen uses, or if a policy in policies.json
    touches browser.aboutwelcome.enabled. Needs a full checkout; reported as not checked otherwise."""
    if not full_checkout:
        print("REVIEW: consent screen not checked against the Firefox code (no full checkout)")
        return
    for rel, needles in CONSENT_SOURCE:
        path = os.path.join(source, rel)
        if not os.path.isfile(path):
            fail("consent screen: %s is missing from the source" % rel)
            continue
        text = read_text(path)
        for n in needles:
            # Whole names only: "uncheckedActionX" must not count as "uncheckedAction".
            if not re.search(r"(?<![\w$])%s(?![\w])" % re.escape(n), text):
                fail("consent screen: %r is no longer in %s" % (n, rel))
    m = re.search(r"const ALLOWED_ABOUT_PAGES = new Set\(\[(.*?)\]\)", read_text(os.path.join(source, SMA_FILE)),
                  re.S)
    if not m or not re.search(r"[\"']home[\"']", m.group(1)):
        fail("consent screen: OPEN_ABOUT_PAGE no longer allows about:home (ALLOWED_ABOUT_PAGES in %s)" % SMA_FILE)
    touching, current = set(), None
    for line in read_text(os.path.join(source, POLICIES_CODE)).splitlines():
        mm = re.match(r"  ([A-Za-z0-9_]+): \{", line)
        if mm:
            current = mm.group(1)
        elif current and "browser.aboutwelcome.enabled" in line:
            touching.add(current)
    for p in sorted(touching - set(WELCOME_OFF_POLICIES) - {"UserMessaging"}):
        print("REVIEW: policy %s also sets browser.aboutwelcome.enabled (%s)" % (p, POLICIES_CODE))
    for p in sorted(touching & set(policies)):
        if p == "UserMessaging" and not policies[p].get("SkipOnboarding"):
            continue
        fail("policy %s sets browser.aboutwelcome.enabled (%s): the consent screen may not show"
             % (p, POLICIES_CODE))


def check_ubo_consent(cfg_text, calls, policies):
    """Fails unless uBlock Origin is installed only through the first-run consent screen."""
    for eid, s in policies.get("ExtensionSettings", {}).items():
        if isinstance(s, dict) and s.get("installation_mode") in SILENT_INSTALL_MODES:
            fail("ExtensionSettings.%s: %s installs it without the user's consent (Store policy 10.1.5)"
                 % (eid, s["installation_mode"]))
    if policies.get("Extensions", {}).get("Install"):
        fail("Extensions.Install installs add-ons without the user's consent (Store policy 10.1.5)")
    for p in WELCOME_OFF_POLICIES:
        if p in policies:
            fail("policy %s locks browser.aboutwelcome.enabled to false: the uBlock Origin consent screen "
                 "would not show" % p)
    if policies.get("UserMessaging", {}).get("SkipOnboarding"):
        fail("UserMessaging.SkipOnboarding switches about:welcome off: the uBlock Origin consent screen "
             "would not show")

    locked = {name: (val or "").strip() for fn, name, val, _ in calls if fn == "lockPref"}
    for name, want in CONSENT_LOCKS + (("browser.aboutwelcome.screens", "JSON.stringify(%s" % CONSENT_VAR),):
        if locked.get(name) != want:
            fail("orbis.cfg: %s must be locked to %s%s" % (name, want, ")" if "(" in want else ""))

    m = re.search(r"^var %s = (\[.*?^\]);" % CONSENT_VAR, cfg_text, re.M | re.S)
    if not m:
        fail("orbis.cfg: no 'var %s = [...];' block" % CONSENT_VAR)
        return
    try:
        screens = json.loads(m.group(1))
    except ValueError as e:
        fail("orbis.cfg: %s is not strict JSON: %s" % (CONSENT_VAR, e))
        return
    installs = find_installs(screens)
    if len(installs) != 1:
        fail("%s: %d INSTALL_ADDON_FROM_URL actions; exactly one (uBlock Origin) is allowed"
             % (CONSENT_VAR, len(installs)))
        return
    path, action = installs[0]
    if action.get("data", {}).get("url") != UBO_AMO_URL:
        fail("%s: the install URL must be %s" % (CONSENT_VAR, UBO_AMO_URL))
    first = screens[0].get("content", {}) if screens else {}
    tiles = first.get("tiles", {})
    items = tiles.get("data", []) if tiles.get("type") == "multiselect" else []
    owner = [i for i, item in enumerate(items) if find_installs(item.get("checkedAction"))]
    if not re.fullmatch(r"screens\[0\]\.content\.tiles\.data\[\d+\]\.checkedAction(\..*)?", path) or not owner:
        fail("%s: the install is at %s; it must be in the checkedAction of a checkbox on the first screen"
             % (CONSENT_VAR, path))
        return
    item = items[owner[0]]
    if item.get("defaultValue") is not True or item.get("type", "checkbox") != "checkbox":
        fail("%s: the uBlock Origin item must be a checkbox with defaultValue true" % CONSENT_VAR)
    button = first.get("primary_button", {}).get("action", {})
    if not (button.get("type") == "MULTI_ACTION" and button.get("collectSelect") is True):
        fail("%s: the first screen's button must be a MULTI_ACTION with collectSelect" % CONSENT_VAR)
    if find_installs(button):
        fail("%s: the first screen's button must not install anything itself" % CONSENT_VAR)
    if not (button.get("navigate") is True and len(screens) >= 2):
        fail("%s: the first screen must navigate to a second screen; leaving about:welcome would cancel the "
             "install while Firefox's permission prompt is open" % CONSENT_VAR)

    # The answer is recorded, and "ask again" reads the same pref and values.
    def set_prefs(action):
        found = []
        if isinstance(action, dict):
            if action.get("type") == "SET_PREF":
                p = action.get("data", {}).get("pref", {})
                found.append((p.get("name"), p.get("value")))
            for v in action.values():
                found += set_prefs(v)
        elif isinstance(action, list):
            for v in action:
                found += set_prefs(v)
        return found
    for key, value in (("checkedAction", "accepted"), ("uncheckedAction", "declined")):
        if (CONSENT_CHOICE_PREF, value) not in set_prefs(item.get(key)):
            fail("%s: %s must SET_PREF %s to %r" % (CONSENT_VAR, key, CONSENT_CHOICE_PREF, value))
    stored = "messaging-system-action." + CONSENT_CHOICE_PREF
    # Ask again until settled (Shibi, 2026-11-12): only "declined" or an installed uBlock Origin (now or at an
    # earlier start) stops it; "accepted" alone must not, since the install may never have happened.
    rearm = re.search(r"getPref\(\"%s\"\)(.*?)clearPref\(\"%s\"\)" % (re.escape(stored), re.escape(MSTONE_PREF)),
                      cfg_text, re.S)
    block = rearm.group(1) if rearm else ""
    if not rearm or "\"declined\"" not in block or UBO_ID not in block or \
            "getPref(\"orbis.ubo.seenInstalled\") !== true" not in block:
        fail("orbis.cfg: no 'ask again' block: it must read %s and clearPref(%s) unless the value is declined or "
             "uBlock Origin is or was installed (Shibi, 2026-11-12)" % (stored, MSTONE_PREF))
    elif "\"accepted\"" in block:
        fail("orbis.cfg: the 'ask again' block must not stop on \"accepted\": accepted without an install is asked "
             "again (Shibi, 2026-11-12)")
    if not re.search(r"defaultPref\(\"browser\.shell\.disableStartMenuPin\", true\)", block):
        fail("orbis.cfg: a repeated ask must not re-pin the MSIX to the Start menu "
             "(defaultPref browser.shell.disableStartMenuPin true in the 'ask again' block)")
    # The decline notice must say plainly that phishing and malware protection is off (Shibi, 2026-11-12).
    notice = json.dumps(item.get("uncheckedNotice", {}))
    for words in ("phishing and malware protection is off", "Google Safe Browsing", "Add-ons and themes"):
        if words not in notice:
            fail("%s: the unchecked notice must say %r" % (CONSENT_VAR, words))


# --------------------------------------------------------------------------------------------------

def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Check Orbis prefs and policies against the Firefox source.")
    ap.add_argument("--source", default=os.path.join(os.environ.get("USERPROFILE", ""),
                                                     "orbis_desktop_src", "firefox"))
    ap.add_argument("--overlay", default=os.path.join(repo, "overlay"))
    ap.add_argument("--settings-doc", default=os.path.join(repo, "docs", "SETTINGS.md"))
    ap.add_argument("--ubo-assets", default=None, help="uBlock Origin assets.json (optional)")
    ap.add_argument("--list", action="store_true", help="print where each pref is defined")
    args = ap.parse_args()

    source = os.path.abspath(args.source)
    for rel in PREF_FILES + (SCHEMA_FILE,):
        if not os.path.isfile(os.path.join(source, rel)):
            print("FAILED: Firefox source file not found: " + os.path.join(source, rel))
            return 1
    full_checkout = os.path.isfile(os.path.join(source, "mach"))

    ff_version = "unknown"
    vf = os.path.join(source, VERSION_FILE)
    if os.path.isfile(vf):
        ff_version = read_text(vf).strip()
    head = ""
    if os.path.isdir(os.path.join(source, ".git")):
        try:
            head = subprocess.run(["git", "-C", source, "rev-parse", "HEAD"], capture_output=True,
                                  text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            head = "(git rev-parse failed)"
    print("Firefox source: %s (version %s%s%s)" % (source, ff_version, ", commit " if head else "", head))
    pin = os.path.join(repo, "upstream", "firefox.json")
    if head and os.path.isfile(pin):
        want = json.loads(read_text(pin)).get("commit", "")
        if want and want != head:
            fail("source checkout is at %s but upstream/firefox.json pins %s" % (head, want))

    defs = load_pref_defs(source)

    # ---- prefs -----------------------------------------------------------------------------------
    cfg_path = os.path.join(args.overlay, "orbis.cfg")
    loader_path = os.path.join(args.overlay, "defaults", "pref", "autoconfig.js")
    cfg_lines = read_text(cfg_path).splitlines()
    if not cfg_lines or not cfg_lines[0].startswith("//"):
        fail("orbis.cfg: line 1 must be a // comment (Firefox skips the first line of the file)")
    calls = parse_cfg_calls(cfg_path, skip_first_line=True)
    loader_calls = parse_cfg_calls(loader_path, skip_first_line=False)

    loader = {name: (val or "").strip() for fn, name, val, _ in loader_calls if fn == "pref"}
    if loader.get("general.config.filename") != "\"orbis.cfg\"":
        fail("autoconfig.js: general.config.filename must be \"orbis.cfg\"")
    if loader.get("general.config.obscure_value") != "0":
        fail("autoconfig.js: general.config.obscure_value must be 0 (plain-text orbis.cfg)")
    if "general.config.sandbox_enabled" in loader:
        fail("autoconfig.js: do not set general.config.sandbox_enabled; orbis.cfg runs sandboxed")

    setters = {}
    for fn, name, val, line in calls:
        if fn in ("lockPref", "defaultPref"):
            if name in setters:
                fail("orbis.cfg:%d: %s is already set on line %d" % (line, name, setters[name]))
            setters[name] = line

    all_calls = [("orbis.cfg", c) for c in calls] + [("autoconfig.js", c) for c in loader_calls]
    names = sorted({c[1] for _, c in all_calls})
    own = [n for n in names if n.startswith(OWN_PREFIXES)]
    missing = [n for n in names if n not in defs and not n.startswith(OWN_PREFIXES)]
    code_refs = {}
    if missing and full_checkout:
        print("Searching the Firefox code for %d pref name(s) not in the pref files..." % len(missing))
        code_refs = search_code(source, set(missing))

    where = {}
    for n in names:
        if n.startswith(OWN_PREFIXES):
            where[n] = "Orbis's own pref"
        elif n in defs:
            d = defs[n]
            where[n] = "; ".join("%s%s" % (x[0].rsplit("/", 1)[-1], (" [" + x[2] + "]") if x[2] else "")
                                 for x in d)
        elif n in code_refs:
            where[n] = "code: " + code_refs[n]
        else:
            where[n] = None
            fail("unknown pref (not in the pref files%s): %s" % (
                ", nor quoted in Firefox code" if full_checkout else "; no full checkout to search", n))

    for src, (fn, name, val, line) in all_calls:
        if val is None or name not in defs:
            continue
        want = {x[1] for x in defs[name]} - {"unknown", "expr"}
        got = literal_type(val)
        if want and got in ("bool", "int", "string") and got not in want:
            if not (got == "string" and "float" in want):
                fail("%s:%d: %s has type %s in Firefox but is set to a %s (%s)" % (
                    src, line, name, "/".join(sorted(want)), got, val.strip()))

    conditional = [n for n in names if n in defs and all(x[2] for x in defs[n])]

    # ---- policies --------------------------------------------------------------------------------
    schema = json.loads(read_text(os.path.join(source, SCHEMA_FILE)))
    pol_path = os.path.join(args.overlay, "distribution", "policies.json")
    try:
        pol_doc = json.loads(read_text(pol_path))
    except ValueError as e:
        fail("policies.json is not valid JSON: %s" % e)
        pol_doc = {}
    if set(pol_doc) != {"policies"}:
        fail("policies.json must have exactly one top-level key, \"policies\"")
    policies = pol_doc.get("policies", {})
    v = Validator(schema, ff_version)
    for pname, pval in policies.items():
        if pname not in schema["properties"]:
            fail("unknown policy: %s" % pname)
            continue
        v.compat(schema["properties"][pname], pname)
        for e in v.errors(pval, schema["properties"][pname], pname):
            fail("policy " + e)

    check_ubo_consent("\n".join(cfg_lines), calls, policies)
    check_consent_source(source, full_checkout, policies)

    # ---- docs/SETTINGS.md ------------------------------------------------------------------------
    doc = read_text(args.settings_doc)
    for n in names:
        if "`%s`" % n not in doc:
            fail("docs/SETTINGS.md has no row for pref `%s`" % n)
    for pname in policies:
        if "`%s`" % pname not in doc:
            fail("docs/SETTINGS.md has no row for policy `%s`" % pname)

    # ---- uBlock Origin lists ---------------------------------------------------------------------
    lists = (policies.get("3rdparty", {}).get("Extensions", {}).get(UBO_ID, {})
             .get("toOverwrite", {}).get("filterLists"))
    if args.ubo_assets:
        assets = json.loads(read_text(args.ubo_assets))
        if not isinstance(lists, list):
            fail("3rdparty: no toOverwrite.filterLists for %s" % UBO_ID)
        else:
            for tok in lists:
                if tok != "user-filters" and tok not in assets and not re.match(r"^[a-z-]+://", tok):
                    fail("uBlock Origin has no filter list %r" % tok)
            defaults = [k for k, a in assets.items() if a.get("content") == "filters"
                        and not a.get("off") and not a.get("lang") and a.get("group") != "regions"]
            for k in defaults:
                if k not in lists:
                    fail("uBlock Origin default list %r is missing from toOverwrite.filterLists" % k)
            print("uBlock Origin defaults (%s): %s" % (args.ubo_assets, ", ".join(defaults)))

    # ---- report ----------------------------------------------------------------------------------
    print("Prefs checked: %d (in pref files: %d, only in code: %d, Orbis's own: %d)" % (
        len(names), len([n for n in names if n in defs]), len(code_refs), len(own)))
    print("Policies checked: %d" % len(policies))
    if args.list:
        for n in names:
            print("  %-62s %s" % (n, where[n] or "NOT FOUND"))
    for n in sorted(code_refs):
        print("REVIEW: %s has no default in the pref files; Firefox code reads it (%s)" % (n, code_refs[n]))
    for n in conditional:
        print("REVIEW: %s is defined only under a build condition: %s" % (n, where[n]))
    if problems:
        for p in problems:
            print("FAIL: " + p)
        print("FAILED: %d problem(s)" % len(problems))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
