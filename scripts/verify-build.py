# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Checks a built Orbis through Marionette: profile location, prefs and policies, uBlock Origin, idle network
lookups, window titles and the About dialog. Used for the first Orbis build; see docs/BUILD.md.

    python -I scripts/verify-build.py PHASE INSTALL_DIR OUT_DIR [EXTRA] [--source DIR] [--profiles DIR]

INSTALL_DIR holds orbis.exe with the Orbis files added (orbis.cfg, defaults/pref/autoconfig.js,
distribution/policies.json; docs/BUILD.md). OUT_DIR receives JSON results, screenshots and logs.

Phases:
  default  Starts Orbis without -profile (its real default profile) and records where the profile is and
           whether the Firefox and Orbis profile folders changed: b-dirs.json, b-before.json, b-after.json.
           Pass: the profile is under %APPDATA%\\Orbis and %LOCALAPPDATA%\\Orbis, and the Mozilla\\Firefox
           profiles.ini and installs.ini hashes are the same before and after. Refuses to start unless
           INSTALL_DIR\\application.ini has Profile=Orbis and RemotingName=orbis (patch 0001 and the mozconfig),
           so that a build without them never opens Firefox's profiles.
  idle     New profile, headless, left idle for 3 minutes with a DNS log (MOZ_LOG timestamp,sync,
           nsHostResolver:5, dns.log*; "sync" writes every line at once, so the release build's fast shutdown
           loses nothing) and TCP sampling of the started process tree (f-tcp.json); then prefs, policies,
           about:policies and uBlock Origin (checks-idle.json, aboutpolicies-idle.json/.png). Nobody answers
           the first-run consent screen here, so uBlock Origin must not be installed.
  consent  First-run uBlock Origin consent screen (EXTRA = accept, decline, close, early or cancel). New profile,
           headless, with the same DNS log. Before the answer: about:welcome shows the screen with the checkbox
           on, and there is no uBlock Origin, no add-on install and no addons.mozilla.org lookup. accept:
           Continue with the checkbox on, accept Firefox's permission prompt; uBlock Origin is installed and its
           selected lists are exactly the 13 lists in policies.json "3rdparty". decline: uncheck (the warning
           about phishing and malware protection must show), Continue; after 60 seconds there is no uBlock
           Origin, no install and no addons.mozilla.org lookup in the whole DNS log. close: leave the screen
           and quit without answering. early: Continue with the checkbox on, then "Start browsing" before
           Firefox's Add prompt is answered. cancel: Continue with the checkbox on, then Cancel in that prompt.
           close, early and cancel leave no uBlock Origin, so the next start must show the screen again
           (without re-pinning the MSIX to the Start menu), where it is declined. accept: uBlock Origin is
           removed again in a later start, which must not bring the question back. All: the choice pref is
           recorded, and two later starts of the same profile do not show the screen again.
           Writes consent-<choice>.json (with a "pass" map and "PASS"/"FAIL"), checks-consent-<choice>.json,
           consent-<choice>-screen.png and the DNS log. "addons.mozilla.org lookup" means any host name ending
           in addons.mozilla.org (also services. and versioncheck-bg.). With --system-locale (for example
           de-DE) the profile pretends that Windows uses that language
           (intl.multilingual.aboutWelcome.systemLocaleOverride), the case in which about:welcome would offer a
           language pack from addons.mozilla.org: run accept and decline with it too.
  second   Second start of an accepted profile (EXTRA = the profile folder, which must be inside --profiles):
           uBlock Origin re-applies its enforced lists at launch (checks-second.json).
  ui       New profile with a window: window titles, brand strings, main window and About dialog screenshots and
           the About dialog text (g-ui.json, g-main-window.png, g-about.png).
  hosts    Reads OUT_DIR's dns.log* files and prints each host name looked up, with a count. No browser.
  quit     Asks a running Orbis on Marionette port EXTRA to quit.

Needs the Marionette client from the Firefox checkout (--source, default %USERPROFILE%\\orbis_desktop_src\\firefox).
Test profiles go to --profiles (default %USERPROFILE%\\orbis_desktop_src\\test-profiles). Every path must be on
drive C:. The browser runs with MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1 so that the checks can read chrome-side state;
the profile's user.js sets remote.prefs.recommended to false, so Marionette does not change network prefs.
Every phase that starts Orbis stops it at the end, also after an error: first through Marionette; if the started
orbis.exe is still running after that, with taskkill /T /F on its PID. Only processes this script started (that
PID and its orbis.exe children) are sampled, read or killed.
"""

import argparse
import collections
import configparser
import glob
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time

UBO = "uBlock0@raymondhill.net"
MOZBASE_MODULES = ["mozrunner", "mozprofile", "mozversion", "mozlog", "mozinfo", "mozfile", "mozprocess",
                   "mozdevice", "mozterm", "mozsystemmonitor", "manifestparser", "mozcrash", "mozscreenshot",
                   "moznetwork"]


def parse_args():
    home = os.environ.get("USERPROFILE", "")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("phase", choices=["default", "idle", "consent", "second", "ui", "hosts", "quit"])
    ap.add_argument("install_dir")
    ap.add_argument("out_dir")
    ap.add_argument("extra", nargs="?",
                    help="consent: accept, decline, close, early or cancel; second: the profile folder; quit: the Marionette port")
    ap.add_argument("--source", default=os.path.join(home, "orbis_desktop_src", "firefox"))
    ap.add_argument("--profiles", default=os.path.join(home, "orbis_desktop_src", "test-profiles"))
    ap.add_argument("--system-locale", default=None,
                    help="consent: Windows language to simulate in the test profile, for example de-DE")
    args = ap.parse_args()
    if args.system_locale and not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", args.system_locale):
        ap.error("--system-locale must be a locale code such as de-DE")
    return args


def real_on_c(path):
    """The full path with junctions and symbolic links resolved; exits unless it is on drive C:."""
    real = os.path.realpath(os.path.abspath(path))
    if real.startswith("\\\\?\\"):
        real = real[4:]
    if not real.upper().startswith("C:\\"):
        sys.exit("REFUSED: every path must be on drive C: '%s' (resolves to '%s')" % (path, real))
    return real


def is_inside(path, root):
    """True if path is strictly below root (both resolved)."""
    return os.path.normcase(path).startswith(os.path.normcase(root.rstrip("\\") + "\\"))


ARGS = parse_args()
INSTALL = real_on_c(ARGS.install_dir)
OUT = real_on_c(ARGS.out_dir)
PROFILES = real_on_c(ARGS.profiles)
SOURCE = real_on_c(ARGS.source)
EXE = os.path.join(INSTALL, "orbis.exe")
os.makedirs(OUT, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def dump(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def load_marionette():
    """Puts the checkout's Marionette client and mozbase on sys.path and returns the Marionette class."""
    src = SOURCE
    client = os.path.join(src, "testing", "marionette", "client")
    if not os.path.isdir(client):
        sys.exit("No Marionette client at %s (use --source)" % client)
    # mozterm is under python/ in Firefox 160, not testing/mozbase; mozlog needs it.
    sys.path[:0] = ([client] + [os.path.join(src, "testing", "mozbase", m) for m in MOZBASE_MODULES]
                    + [os.path.join(src, "python", "mozterm")])
    from marionette_driver.marionette import Marionette
    return Marionette


def tree_state():
    """Existence, top-level entries and .ini hashes of the Mozilla and Orbis profile roots."""
    res = {}
    for root in [os.path.expandvars(r"%APPDATA%\Mozilla\Firefox"),
                 os.path.expandvars(r"%LOCALAPPDATA%\Mozilla\Firefox"),
                 os.path.expandvars(r"%APPDATA%\Mozilla"),
                 os.path.expandvars(r"%LOCALAPPDATA%\Mozilla"),
                 os.path.expandvars(r"%APPDATA%\Orbis"),
                 os.path.expandvars(r"%LOCALAPPDATA%\Orbis")]:
        entry = {"exists": os.path.isdir(root)}
        if entry["exists"]:
            entry["top"] = sorted(os.listdir(root))
            for ini in ("profiles.ini", "installs.ini"):
                p = os.path.join(root, ini)
                if os.path.isfile(p):
                    with open(p, "rb") as f:
                        entry[ini] = hashlib.sha256(f.read()).hexdigest()
        res[root] = entry
    return res


def launch(profile, port, headless=True, extra_env=None, no_profile=False, extra_prefs=None):
    env = dict(os.environ)
    env["MOZ_REMOTE_ALLOW_SYSTEM_ACCESS"] = "1"
    for k in ("XRE_PROFILE_PATH", "MOZ_HEADLESS"):
        env.pop(k, None)
    if extra_env:
        env.update(extra_env)
    args = [EXE, "--marionette"]
    if headless:
        args.append("--headless")
    if not no_profile:
        os.makedirs(profile, exist_ok=True)
        with open(os.path.join(profile, "user.js"), "w") as f:
            f.write('user_pref("marionette.port", %d);\n' % port)
            # Marionette must not apply its recommended (automation) prefs: they change network behaviour.
            f.write('user_pref("remote.prefs.recommended", false);\n')
            for k, v in (extra_prefs or {}).items():
                f.write("user_pref(%s, %s);\n" % (json.dumps(k), json.dumps(v)))
        args += ["-profile", profile, "--new-instance"]
    log("launch:", args)
    return subprocess.Popen(args, env=env)


def connect(port, timeout=90):
    Marionette = load_marionette()
    end = time.time() + timeout
    while True:
        try:
            m = Marionette(host="127.0.0.1", port=port, startup_timeout=10)
            m.start_session()
            return m
        except Exception as e:  # noqa: BLE001
            if time.time() > end:
                raise
            log("waiting for marionette:", type(e).__name__)
            time.sleep(3)


def new_profile(kind):
    """A new profile folder name under PROFILES, unique per run (date, time to the second, random suffix)."""
    return os.path.join(PROFILES, "%s-%s-%s" % (kind, time.strftime("%Y%m%d-%H%M%S"), secrets.token_hex(3)))


def process_tree(root_pid):
    """PIDs of root_pid and its descendants, following parent links, keeping only orbis.exe processes."""
    ps = ("Get-CimInstance Win32_Process | ForEach-Object "
          "{ '{0} {1} {2}' -f $_.ProcessId, $_.ParentProcessId, $_.Name }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    children = collections.defaultdict(list)
    names = {}
    for line in r.stdout.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            pid, ppid = int(parts[0]), int(parts[1])
            names[pid] = parts[2].strip().lower()
            if pid != ppid:
                children[ppid].append(pid)
    found, todo = set(), [root_pid]
    while todo:
        pid = todo.pop()
        if pid in found or names.get(pid) != "orbis.exe":
            continue
        found.add(pid)
        todo.extend(children.get(pid, []))
    return found


def stop_browser(proc, m=None):
    """Quits the started Orbis through Marionette (if connected); then kills what is left of its process tree."""
    if proc is None:
        return
    tree = process_tree(proc.pid) if proc.poll() is None else set()
    if m is not None:
        try:
            m._send_message("Marionette:Quit", {"flags": ["eAttemptQuit"]})
        except Exception as e:  # noqa: BLE001
            log("quit message:", type(e).__name__, e)
    try:
        proc.wait(60 if m is not None else 1)
    except subprocess.TimeoutExpired:
        log("Orbis still running: taskkill /T /F /PID %d" % proc.pid)
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            log("WARNING: PID %d did not exit" % proc.pid)
    # Child processes that outlived the started orbis.exe: same PIDs, and still orbis.exe children of that tree.
    left = tree & set(process_tree_names_orbis())
    for pid in sorted(left - {proc.pid}):
        log("taskkill /F /PID %d (left over from the started Orbis)" % pid)
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    log("exit code", proc.returncode)


def process_tree_names_orbis():
    """PIDs of all running orbis.exe processes (used only to intersect with a tree recorded earlier)."""
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "(Get-Process orbis -ErrorAction SilentlyContinue).Id"], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split() if x.isdigit()]


def chrome(m, script, args=None):
    with m.using_context("chrome"):
        return m.execute_async_script(script, script_args=args or [], script_timeout=60000)


def win_titles(root_pid):
    """Visible top-level window titles of the started orbis.exe and its child processes (Win32)."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    pids = process_tree(root_pid)
    titles = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(512)
            u.GetWindowTextW(h, buf, 512)
            if buf.value:
                titles.append(buf.value)
        return True
    u.EnumWindows(cb, 0)
    return titles


PREFS = [
    "browser.safebrowsing.malware.enabled", "browser.safebrowsing.phishing.enabled",
    "browser.safebrowsing.downloads.remote.enabled", "browser.safebrowsing.provider.google4.updateURL",
    "browser.safebrowsing.provider.google5.enabled", "toolkit.telemetry.enabled", "toolkit.telemetry.unified",
    "toolkit.telemetry.server", "datareporting.healthreport.uploadEnabled",
    "datareporting.policy.dataSubmissionEnabled", "app.normandy.enabled", "app.shield.optoutstudies.enabled",
    "nimbus.rollouts.enabled", "media.gmp-widevinecdm.allow-chromium-update",
    "extensions.getAddons.cache.enabled", "browser.topsites.contile.enabled", "browser.region.update.enabled",
    "browser.newtabpage.activity-stream.default.sites",
    "identity.fxaccounts.enabled", "dom.security.https_only_mode", "dom.security.https_only_mode_pbm",
    "browser.contentblocking.category", "privacy.trackingprotection.enabled",
    "privacy.trackingprotection.socialtracking.enabled", "network.cookie.cookieBehavior",
    "orbis.privacy.etpStrictApplied", "network.captive-portal-service.enabled",
    "network.connectivity-service.enabled", "network.trr.mode", "media.eme.enabled",
    "general.config.filename", "app.update.enabled",
    "browser.aboutwelcome.enabled", "browser.aboutwelcome.experimentsGate.enabled",
    "startup.homepage_welcome_url", "messaging-system-action.orbis.ubo.consent",
    "intl.multilingual.aboutWelcome.languageMismatchEnabled", "trailhead.firstrun.didHandleCampaignAction",
    "network.dns.disablePrefetch", "network.prefetch-next", "network.http.speculative-parallel-limit",
]
CONSENT_PREF = "messaging-system-action.orbis.ubo.consent"
AMO_HOST = "addons.mozilla.org"
LOCALE_OVERRIDE_PREF = "intl.multilingual.aboutWelcome.systemLocaleOverride"

CHECK_JS = r"""
const [prefs, ubo, done] = [arguments[0], arguments[1], arguments[arguments.length - 1]];
(async () => {
  const out = {};
  try {
    out.appinfo = {name: Services.appinfo.name, version: Services.appinfo.version,
                   vendor: Services.appinfo.vendor, ua: navigator.userAgent};
    out.profD = Services.dirsvc.get("ProfD", Ci.nsIFile).path;
    out.policiesStatus = Services.policies.status;
    out.STATUS_ACTIVE = Ci.nsIEnterprisePolicies.ACTIVE;
    out.activePolicies = Services.policies.getActivePolicies();
    out.uboManaged = Services.policies.getExtensionPolicy ? Services.policies.getExtensionPolicy(ubo) : null;
    out.prefs = {};
    for (const p of prefs) {
      const t = Services.prefs.getPrefType(p);
      let v = null;
      if (t == Services.prefs.PREF_BOOL) v = Services.prefs.getBoolPref(p);
      else if (t == Services.prefs.PREF_INT) v = Services.prefs.getIntPref(p);
      else if (t == Services.prefs.PREF_STRING) v = Services.prefs.getStringPref(p);
      out.prefs[p] = {value: v, locked: Services.prefs.prefIsLocked(p),
                      userSet: Services.prefs.prefHasUserValue(p), exists: t != 0};
    }
    // Policy errors: about:policies lists errors from the policies-errors console.
    try {
      const msgs = Services.console.getMessageArray() || [];
      out.policyConsole = msgs.map(m => m.message || String(m)).filter(s => /polic/i.test(s)).slice(-30);
    } catch (e) { out.policyConsole = String(e); }
    const { AddonManager } = ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
    const a = await AddonManager.getAddonByID(ubo);
    out.ubo = a ? {id: a.id, name: a.name, version: a.version, isActive: a.isActive, userDisabled: a.userDisabled,
                   appDisabled: a.appDisabled, signedState: a.signedState, installTelemetryInfo: a.installTelemetryInfo,
                   sourceURI: a.sourceURI && a.sourceURI.spec, permissions: a.permissions} : null;
    if (a && a.isActive) {
      const pol = WebExtensionPolicy.getByID(ubo);
      out.uboUUID = pol && pol.mozExtensionHostname;
      const { ExtensionStorageIDB } = ChromeUtils.importESModule("resource://gre/modules/ExtensionStorageIDB.sys.mjs");
      const ext = pol.extension;
      out.uboIDBMigrated = ExtensionStorageIDB.isMigratedExtension(ext);
      const db = await ExtensionStorageIDB.open(ExtensionStorageIDB.getStoragePrincipal(ext), false);
      const st = await db.get(["selectedFilterLists", "availableFilterLists", "lastRestoreFile", "version"]);
      out.uboStorageKeys = Object.keys(st);
      out.selectedFilterLists = st.selectedFilterLists || null;
      out.uboVersionStored = st.version;
      const all = await db.get(null);
      out.uboAllKeys = Object.keys(all).slice(0, 80);
    }
  } catch (e) { out.error = String(e) + "\n" + e.stack; }
  done(out);
})();
"""


def run_checks(m, tag):
    res = chrome(m, CHECK_JS, [PREFS, UBO])
    dump("checks-%s.json" % tag, res)
    try:
        m.navigate("about:policies")
        time.sleep(2)
        res2 = m.execute_script("""
          const act = document.getElementById('active');
          return {title: document.title, activeTabClasses: act.className,
                  errorsTabHidden: document.getElementById('category-errors').hidden,
                  errorRows: document.querySelectorAll('#errorsContent tr').length,
                  activeRows: document.querySelectorAll('#activeContent > tr').length,
                  activePolicyNames: Array.from(document.querySelectorAll('#activeContent > tr > td:first-child'))
                      .map(e => e.textContent.trim()).filter(Boolean)};
        """)
        m.navigate("about:policies#errors")
        time.sleep(1)
        res2["errorsText"] = m.execute_script(
            "const e=document.querySelector('#errors'); return e ? e.textContent.trim().slice(0,2000) : null;")
        dump("aboutpolicies-%s.json" % tag, res2)
        m.navigate("about:policies#active")
        time.sleep(1)
        with open(os.path.join(OUT, "aboutpolicies-%s.png" % tag), "wb") as f:
            f.write(m.screenshot(format="binary"))
    except Exception as e:  # noqa: BLE001
        dump("aboutpolicies-%s.json" % tag, {"error": repr(e)})
    return res


def sample_tcp(conns, root_pid):
    """Adds the remote (address, port) pairs of the started process tree's TCP connections to conns."""
    pids = process_tree(root_pid)
    if not pids:
        return
    ps = ("$p = @(" + ",".join(str(p) for p in sorted(pids)) + "); "
          "if ($p) { Get-NetTCPConnection -OwningProcess $p -ErrorAction SilentlyContinue | "
          "Where-Object { $_.RemoteAddress -notin '0.0.0.0','::','127.0.0.1','::1' } | "
          "ForEach-Object { '{0} {1} {2} {3}' -f $_.OwningProcess, $_.RemoteAddress, $_.RemotePort, $_.State } }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 4:
            conns.add((parts[1], parts[2]))


def check_application_ini():
    """Exits unless application.ini keeps Orbis's profiles and remoting apart from Firefox's."""
    path = os.path.join(INSTALL, "application.ini")
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    try:
        with open(path, encoding="utf-8") as f:
            cp.read_file(f)
        profile = cp.get("App", "Profile", fallback=None)
        remoting = cp.get("App", "RemotingName", fallback=None)
    except (OSError, configparser.Error) as e:
        sys.exit("REFUSED: cannot read %s: %s" % (path, e))
    if profile != "Orbis" or remoting != "orbis":
        sys.exit("REFUSED: %s has Profile=%s and RemotingName=%s; the default phase needs Profile=Orbis and "
                 "RemotingName=orbis, or it would use Firefox's profiles" % (path, profile, remoting))


def phase_default():
    check_application_ini()
    before = tree_state()
    dump("b-before.json", before)
    proc = m = None
    try:
        proc = launch(None, 2828, headless=True, no_profile=True)
        m = connect(2828)
        time.sleep(20)
        info = chrome(m, "const d=arguments[arguments.length-1];"
                         " d({profD: Services.dirsvc.get('ProfD', Ci.nsIFile).path,"
                         " localD: Services.dirsvc.get('ProfLD', Ci.nsIFile).path,"
                         " defRoot: Services.dirsvc.get('DefProfRt', Ci.nsIFile).path});")
        dump("b-dirs.json", info)
    finally:
        stop_browser(proc, m)
    time.sleep(3)
    after = tree_state()
    dump("b-after.json", after)
    log(json.dumps({"dirs": info, "before": before, "after": after}, indent=1))


def phase_idle():
    prof = new_profile("idle")
    dnslog = os.path.join(OUT, "dns.log")
    proc = m = None
    try:
        proc = launch(prof, 28282, headless=True,
                      extra_env={"MOZ_LOG": "timestamp,sync,nsHostResolver:5", "MOZ_LOG_FILE": dnslog})
        conns = set()
        t0 = time.time()
        while time.time() - t0 < 180:
            sample_tcp(conns, proc.pid)
            time.sleep(4)
        dump("f-tcp.json", sorted(conns))
        m = connect(28282)
        res = run_checks(m, "idle")
        sample_tcp(conns, proc.pid)
        dump("f-tcp.json", sorted(conns))
    finally:
        stop_browser(proc, m)
    log("profile:", prof)
    log(json.dumps({k: res.get(k) for k in ("policiesStatus", "ubo", "selectedFilterLists", "error")}, indent=1))


ADDON_STATE_JS = r"""
const [ubo, pref, done] = [arguments[0], arguments[1], arguments[arguments.length - 1]];
(async () => {
  const out = {};
  try {
    const { AddonManager } = ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
    const a = await AddonManager.getAddonByID(ubo);
    out.ubo = a ? {version: a.version, isActive: a.isActive} : null;
    out.installs = (await AddonManager.getAllInstalls()).map(i => ({
      id: i.addon ? i.addon.id : (i.existingAddon ? i.existingAddon.id : null),
      url: i.sourceURI && i.sourceURI.spec, state: i.state, error: i.error}));
    out.choice = Services.prefs.getPrefType(pref) ? Services.prefs.getStringPref(pref) : null;
    out.seenInstalled = Services.prefs.getBoolPref("orbis.ubo.seenInstalled", false);
    // true only on a repeated ask: Firefox must not re-pin the MSIX to the Start menu then.
    out.startMenuPinOff = Services.prefs.getBoolPref("browser.shell.disableStartMenuPin", false);
    out.tabs = [];
    for (const w of Services.wm.getEnumerator("navigator:browser")) {
      for (const b of w.gBrowser.browsers) out.tabs.push(b.currentURI.spec);
    }
    const n = Services.wm.getMostRecentWindow("navigator:browser")
      ?.PopupNotifications?.getNotification("addon-webext-permissions");
    out.permissionPrompt = n ? {message: n.message && String(n.message)} : null;
  } catch (e) { out.error = String(e) + "\n" + e.stack; }
  done(out);
})();
"""

CANCEL_PROMPT_JS = r"""
const done = arguments[arguments.length - 1];
const n = Services.wm.getMostRecentWindow("navigator:browser").PopupNotifications
  .getNotification("addon-webext-permissions");
if (!n) { done(false); } else { n.secondaryActions[0].callback(); done(true); }
"""

UNINSTALL_UBO_JS = r"""
const [ubo, done] = [arguments[0], arguments[arguments.length - 1]];
(async () => {
  const { AddonManager } = ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
  const a = await AddonManager.getAddonByID(ubo);
  if (a) { await a.uninstall(); }
  done(!!a);
})();
"""

ACCEPT_PROMPT_JS = r"""
const done = arguments[arguments.length - 1];
const w = Services.wm.getMostRecentWindow("navigator:browser");
const n = w.PopupNotifications.getNotification("addon-webext-permissions");
if (!n) { done(false); }
else {
  // The prompt's own "Add" button when the panel is shown; its main action otherwise (headless).
  const el = w.document.getElementById("addon-webext-permissions-notification");
  if (el && el.button && !el.hidden) { el.button.click(); done("button"); }
  else { n.mainAction.callback(); done("mainAction"); }
}
"""


def dns_hosts(folder):
    """Host name -> number of lookups, from the dns.log* files in folder (MOZ_LOG nsHostResolver:5)."""
    counts = collections.Counter()
    for path in sorted(glob.glob(os.path.join(folder, "dns.log*"))):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                for host in re.findall(r"Resolving host \[([^\]]+)\]", line):
                    counts[host] += 1
    return counts


def amo_lookups(hosts):
    """Lookups of addons.mozilla.org and its subdomains (services., versioncheck-bg.) in a dns_hosts() result."""
    return sum(n for h, n in hosts.items() if h == AMO_HOST or h.endswith("." + AMO_HOST))


def expected_lists():
    """uBlock Origin's toOverwrite.filterLists from the policies.json that the tested install uses."""
    with open(os.path.join(INSTALL, "distribution", "policies.json"), encoding="utf-8") as f:
        pol = json.load(f)["policies"]
    return pol["3rdparty"]["Extensions"][UBO]["toOverwrite"]["filterLists"]


def wait_for(m, what, test, timeout, step=2):
    """Polls ADDON_STATE_JS until test(state) is true or timeout seconds pass; returns the last state."""
    end = time.time() + timeout
    while True:
        st = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
        if test(st) or time.time() > end:
            log("%s: %s" % (what, "yes" if test(st) else "TIMEOUT"))
            return st
        time.sleep(step)


def switch_to_welcome(m):
    """Switches Marionette's content context to the about:welcome tab; returns True when found."""
    for h in m.window_handles:
        m.switch_to_window(h)
        if m.get_url().startswith("about:welcome"):
            return True
    return False


CONSENT_CHOICES = ("accept", "decline", "close", "early", "cancel")
# Choices that leave the question unsettled, so the next start must ask again.
ASK_AGAIN_CHOICES = ("close", "early", "cancel")


def welcome_open(m):
    """Waits for the about:welcome tab; returns the last add-on state."""
    st = wait_for(m, "about:welcome open", lambda s: any(t.startswith("about:welcome") for t in s["tabs"]), 60)
    time.sleep(5)  # the page renders its screen after it has loaded
    return st


def check_screen(m, res, ok, tag, prev_choice=None, amo_base=0):
    """Records the unanswered screen: shown, checked by default, no uBlock Origin, no AMO lookup yet. On a
    repeated ask, prev_choice is the choice already stored and amo_base the AMO lookups of the earlier starts."""
    b = res[tag + "Before"] = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
    res[tag + "AmoLookupsBefore"] = amo_lookups(dns_hosts(OUT)) - amo_base
    if not switch_to_welcome(m):
        raise RuntimeError("no about:welcome tab: %r" % b["tabs"])
    box = m.find_element("css selector", "#orbis-install-ubo")
    res[tag + "ScreenText"] = m.execute_script("return document.body.innerText")
    ok[tag + "ScreenShown"] = "Install uBlock Origin ad blocker" in res[tag + "ScreenText"]
    ok[tag + "CheckedByDefault"] = box.is_selected() is True
    ok[tag + "NoUboBeforeConsent"] = b["ubo"] is None and not b["installs"] and b["choice"] == prev_choice
    ok[tag + "NoAmoBeforeConsent"] = res[tag + "AmoLookupsBefore"] == 0
    return box


def decline_on_screen(m, res, ok, box, shot):
    """Unchecks the box, checks the warning, saves a screenshot and clicks Continue."""
    box.click()
    time.sleep(1)
    res["screenTextUnchecked"] = text = m.execute_script("return document.body.innerText")
    ok["uncheckedByClick"] = box.is_selected() is False
    ok["warnsNoPhishingMalwareProtection"] = all(
        s in text for s in ("phishing and malware", "Google Safe Browsing", "Strict tracking protection stays on",
                            "Add-ons and themes"))
    with open(os.path.join(OUT, shot), "wb") as f:
        f.write(m.screenshot(format="binary"))
    m.find_element("css selector", "button.primary").click()
    log("clicked Continue (box unchecked)")


def phase_consent():
    """accept, decline: answer on the first start. close: leave the screen and quit without answering. early:
    Continue with the box checked, then "Start browsing" at once, before Firefox's Add prompt is answered.
    cancel: Continue with the box checked, then Cancel in Firefox's prompt. close, early and cancel leave the
    question unsettled: the next start must show the screen again (and must not re-pin the MSIX to the Start
    menu); it is declined there. accept: in the first later start uBlock Origin is removed again. All: the two
    later starts must not show the screen."""
    choice = ARGS.extra
    if choice not in CONSENT_CHOICES:
        sys.exit("consent: give one of %s as EXTRA" % ", ".join(CONSENT_CHOICES))
    prof = new_profile("consent-" + choice)
    res = {"choice": choice, "profile": prof, "systemLocale": ARGS.system_locale, "pass": {}}
    prefs = {LOCALE_OVERRIDE_PREF: ARGS.system_locale} if ARGS.system_locale else None
    ok = res["pass"]

    def start(logname):
        return launch(prof, 28284, headless=True, extra_prefs=prefs,
                      extra_env={"MOZ_LOG": "timestamp,sync,nsHostResolver:5",
                                 "MOZ_LOG_FILE": os.path.join(OUT, logname)})

    proc = m = None
    try:
        proc = start("dns.log")
        m = connect(28284)
        welcome_open(m)
        box = check_screen(m, res, ok, "first")
        if choice == "decline":
            decline_on_screen(m, res, ok, box, "consent-decline-screen.png")
        elif choice == "close":
            with open(os.path.join(OUT, "consent-close-screen.png"), "wb") as f:
                f.write(m.screenshot(format="binary"))
            m.navigate("about:blank")  # the user leaves the screen without answering ...
            time.sleep(2)
            res["afterLeaving"] = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
            ok["noChoiceAfterLeaving"] = res["afterLeaving"]["choice"] is None
        else:
            with open(os.path.join(OUT, "consent-%s-screen.png" % choice), "wb") as f:
                f.write(m.screenshot(format="binary"))
            m.find_element("css selector", "button.primary").click()
            log("clicked Continue (box checked)")

        if choice == "accept":
            st = wait_for(m, "permission prompt", lambda s: s["permissionPrompt"] or s["ubo"], 90)
            res["permissionPrompt"] = st["permissionPrompt"]
            if st["permissionPrompt"]:
                res["promptAcceptedBy"] = chrome(m, ACCEPT_PROMPT_JS)
            wait_for(m, "uBlock Origin active", lambda s: s["ubo"] and s["ubo"]["isActive"], 120)
            # The second screen ("Installing uBlock Origin...") stays until the user starts browsing.
            if switch_to_welcome(m):
                res["secondScreenText"] = m.execute_script("return document.body.innerText")
                m.find_element("css selector", "button.primary").click()
            st = wait_for(m, "home page", lambda s: "about:home" in s["tabs"], 30)
            ok["finishedOnHome"] = st["tabs"] == ["about:home"]
            want = expected_lists()
            end = time.time() + 180
            while True:
                checks = run_checks(m, "consent-accept")
                if sorted(checks.get("selectedFilterLists") or []) == sorted(want) or time.time() > end:
                    break
                time.sleep(10)
            res["after"] = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
            res["selectedFilterLists"] = checks.get("selectedFilterLists")
            ok["uboInstalled"] = bool(res["after"]["ubo"] and res["after"]["ubo"]["isActive"])
            ok["lists13"] = len(want) == 13 and sorted(res["selectedFilterLists"] or []) == sorted(want)
            ok["choiceRecorded"] = res["after"]["choice"] == "accepted"
        elif choice == "early":
            # "Start browsing" on the second screen at once, without answering Firefox's prompt.
            time.sleep(1)
            if not switch_to_welcome(m):
                raise RuntimeError("the second screen is gone")
            res["secondScreenText"] = m.execute_script("return document.body.innerText")
            m.find_element("css selector", "button.primary").click()
            log("clicked Start browsing before the prompt was answered")
            time.sleep(30)
            a = res["after"] = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
            ok["noUboWithoutAdd"] = a["ubo"] is None and not a["installs"] and a["permissionPrompt"] is None
            ok["choiceRecorded"] = a["choice"] == "accepted"
            ok["finishedOnHome"] = a["tabs"] == ["about:home"]
        elif choice == "cancel":
            st = wait_for(m, "permission prompt", lambda s: s["permissionPrompt"] or s["ubo"], 90)
            res["promptCancelled"] = chrome(m, CANCEL_PROMPT_JS)
            time.sleep(10)
            if switch_to_welcome(m):
                m.find_element("css selector", "button.primary").click()  # Start browsing
            time.sleep(5)
            a = res["after"] = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
            ok["promptShownAndCancelled"] = res["promptCancelled"] is True
            ok["noUboAfterCancel"] = a["ubo"] is None and not a["installs"]
            ok["choiceRecorded"] = a["choice"] == "accepted"
        elif choice == "decline":
            time.sleep(60)
            a = res["after"] = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
            run_checks(m, "consent-decline")
            ok["noUbo"] = a["ubo"] is None and not a["installs"] and a["permissionPrompt"] is None
            ok["choiceRecorded"] = a["choice"] == "declined"
            ok["finishedOnHome"] = a["tabs"] == ["about:home"]
    finally:
        stop_browser(proc, m)

    if choice in ASK_AGAIN_CHOICES:
        # Orbis starts again: the screen must come back. Answer it this time (decline).
        prev_choice = (res.get("after") or {}).get("choice")
        amo_base = amo_lookups(dns_hosts(OUT))
        proc = m = None
        try:
            proc = start("dns.log.start2")
            m = connect(28284)
            st = welcome_open(m)
            ok["askedAgain"] = any(t.startswith("about:welcome") for t in st["tabs"])
            ok["noStartMenuRepinOnAskAgain"] = st["startMenuPinOff"] is True
            ok["startMenuPinAllowedOnRealFirstRun"] = res["firstBefore"]["startMenuPinOff"] is False
            box = check_screen(m, res, ok, "again", prev_choice, amo_base)
            decline_on_screen(m, res, ok, box, "consent-close-again-screen.png")
            time.sleep(20)
            a = res["after"] = chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF])
            ok["noUbo"] = a["ubo"] is None and not a["installs"]
            ok["choiceDeclinedOnAskAgain"] = a["choice"] == "declined"
        finally:
            stop_browser(proc, m)

    hosts = dns_hosts(OUT)
    res["dnsHosts"] = dict(sorted(hosts.items()))
    if choice == "accept":
        ok["amoLookupAfterConsent"] = hosts.get(AMO_HOST, 0) > 0
    elif choice in ("decline", "close"):
        ok["noAmoLookup"] = amo_lookups(hosts) == 0
    # Later starts of the same profile: after an answer the screen must never come back.
    res["laterStarts"] = []
    for i in range(2):
        proc = m = None
        try:
            proc = launch(prof, 28284, headless=True)
            m = connect(28284)
            time.sleep(15)
            res["laterStarts"].append(chrome(m, ADDON_STATE_JS, [UBO, CONSENT_PREF]))
            if choice == "accept" and i == 0:
                # The user removes uBlock Origin later: that must not bring the question back.
                ok["seenInstalledRecorded"] = res["laterStarts"][0]["seenInstalled"] is True
                ok["uboRemoved"] = chrome(m, UNINSTALL_UBO_JS, [UBO]) is True
        finally:
            stop_browser(proc, m)
    ok["notAskedAgain"] = not any(t.startswith("about:welcome") for s in res["laterStarts"] for t in s["tabs"])
    ok["noStartMenuPinOffWhenSettled"] = not any(s["startMenuPinOff"] for s in res["laterStarts"])
    res["result"] = "PASS" if ok and all(ok.values()) else "FAIL"
    dump("consent-%s.json" % choice, res)
    log(json.dumps({k: res[k] for k in ("pass", "result", "profile")}, indent=1))


def phase_second():
    if not ARGS.extra:
        sys.exit("second: give the idle profile folder as EXTRA")
    prof = real_on_c(ARGS.extra)
    if not is_inside(prof, PROFILES) or not os.path.isdir(prof):
        sys.exit("REFUSED: the profile must be an existing folder inside %s: '%s'" % (PROFILES, prof))
    proc = m = None
    try:
        proc = launch(prof, 28282, headless=True)
        m = connect(28282)
        time.sleep(30)
        res = run_checks(m, "second")
    finally:
        stop_browser(proc, m)
    log(json.dumps({k: res.get(k) for k in ("ubo", "selectedFilterLists", "uboStorageKeys", "error")}, indent=1))


def phase_ui():
    prof = new_profile("ui")
    proc = m = None
    try:
        proc = launch(prof, 28283, headless=False)
        m = connect(28283)
        out = ui_checks(m, proc.pid)
    finally:
        stop_browser(proc, m)
    log(json.dumps({k: v for k, v in out.items() if k != "aboutText"}, indent=1))


def ui_checks(m, root_pid):
    time.sleep(8)
    out = {}
    with m.using_context("chrome"):
        out["windowTitle"] = m.title
        out["docTitle"] = m.execute_script("return document.title")
        out["brand"] = m.execute_script("""
          const b = Services.strings.createBundle('chrome://branding/locale/brand.properties');
          return {short: b.GetStringFromName('brandShortName'), full: b.GetStringFromName('brandFullName')};""")
        out["win32TitlesMain"] = win_titles(root_pid)
        with open(os.path.join(OUT, "g-main-window.png"), "wb") as f:
            f.write(m.screenshot(format="binary"))
        dump("g-ui.json", out)
        main = m.current_chrome_window_handle
        m.execute_script("window.openDialog('chrome://browser/content/aboutDialog.xhtml', 'Browser:About',"
                         " 'chrome,resizable=no,minimizable=no,centerscreen');")
        time.sleep(4)
        for h in m.chrome_window_handles:
            if h != main:
                m.switch_to_window(h)
                break
        out["aboutTitle"] = m.title
        # textContent includes hidden elements (for example the ESR label); aboutVisibleText does not.
        out["aboutText"] = m.execute_script("return document.documentElement.textContent.replace(/\\s+/g,' ').trim()")
        out["aboutVisibleText"] = m.execute_script(
            "const c=document.getElementById('aboutDialogContainer');"
            " return c ? c.innerText.replace(/\\s+/g,' ').trim() : null")
        out["aboutLinks"] = m.execute_script(
            "return Array.from(document.querySelectorAll('[href]')).filter(e => e.getClientRects().length)"
            ".map(e => e.getAttribute('href'))")
        out["aboutVersion"] = m.execute_script(
            "const v=document.getElementById('version'); return v ? v.textContent : null")
        with open(os.path.join(OUT, "g-about.png"), "wb") as f:
            f.write(m.screenshot(format="binary"))
        out["win32TitlesWithAbout"] = win_titles(root_pid)
        dump("g-ui.json", out)
        m.execute_script("window.close()")
        time.sleep(1)
        m.switch_to_window(m.chrome_window_handles[0])
        out["win32Titles"] = win_titles(root_pid)
    dump("g-ui.json", out)
    return out


def phase_hosts():
    if not glob.glob(os.path.join(OUT, "dns.log*")):
        sys.exit("No dns.log* files in %s (run the idle or consent phase first)" % OUT)
    for host, n in sorted(dns_hosts(OUT).items()):
        print("%5d  %s" % (n, host))


def phase_quit():
    if not ARGS.extra:
        sys.exit("quit: give the Marionette port as EXTRA")
    Marionette = load_marionette()
    m = Marionette(host="127.0.0.1", port=int(ARGS.extra))
    m.start_session()
    m._send_message("Marionette:Quit", {"flags": ["eAttemptQuit"]})


if __name__ == "__main__":
    if ARGS.phase not in ("hosts", "quit") and not os.path.isfile(EXE):
        sys.exit("No orbis.exe in %s" % INSTALL)
    {"default": phase_default, "idle": phase_idle, "consent": phase_consent, "second": phase_second, "ui": phase_ui,
     "hosts": phase_hosts, "quit": phase_quit}[ARGS.phase]()
