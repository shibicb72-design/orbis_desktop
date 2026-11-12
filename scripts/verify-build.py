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
           profiles.ini and installs.ini hashes are the same before and after.
  idle     New profile, headless, left idle for 3 minutes with a DNS log (MOZ_LOG nsHostResolver:5, dns.log*)
           and TCP sampling (f-tcp.json); then prefs, policies, about:policies and uBlock Origin's filter lists
           (checks-idle.json, aboutpolicies-idle.json/.png).
  second   Second start of an idle profile (EXTRA = the profile folder): uBlock Origin re-applies its enforced
           lists at launch (checks-second.json).
  ui       New profile with a window: window titles, brand strings, main window and About dialog screenshots and
           the About dialog text (g-ui.json, g-main-window.png, g-about.png).
  hosts    Reads OUT_DIR's dns.log* files and prints each host name looked up, with a count. No browser.
  quit     Asks a running Orbis on Marionette port EXTRA to quit.

Needs the Marionette client from the Firefox checkout (--source, default %USERPROFILE%\\orbis_desktop_src\\firefox).
Test profiles go to --profiles (default %USERPROFILE%\\orbis_desktop_src\\test-profiles). Every path must be on
drive C:. The browser runs with MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1 so that the checks can read chrome-side state;
the profile's user.js sets remote.prefs.recommended to false, so Marionette does not change network prefs.
"""

import argparse
import collections
import glob
import hashlib
import json
import os
import re
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
    ap.add_argument("phase", choices=["default", "idle", "second", "ui", "hosts", "quit"])
    ap.add_argument("install_dir")
    ap.add_argument("out_dir")
    ap.add_argument("extra", nargs="?", help="second: the profile folder; quit: the Marionette port")
    ap.add_argument("--source", default=os.path.join(home, "orbis_desktop_src", "firefox"))
    ap.add_argument("--profiles", default=os.path.join(home, "orbis_desktop_src", "test-profiles"))
    return ap.parse_args()


ARGS = parse_args()
INSTALL = os.path.abspath(ARGS.install_dir)
OUT = os.path.abspath(ARGS.out_dir)
PROFILES = os.path.abspath(ARGS.profiles)
EXE = os.path.join(INSTALL, "orbis.exe")

for _p in (INSTALL, OUT, PROFILES, os.path.abspath(ARGS.source)):
    if not _p.upper().startswith("C:\\"):
        sys.exit("REFUSED: every path must be on drive C: '%s'" % _p)
os.makedirs(OUT, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def dump(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def load_marionette():
    """Puts the checkout's Marionette client and mozbase on sys.path and returns the Marionette class."""
    src = os.path.abspath(ARGS.source)
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


def launch(profile, port, headless=True, extra_env=None, no_profile=False):
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


def quit_browser(m, proc):
    try:
        m._send_message("Marionette:Quit", {"flags": ["eAttemptQuit"]})
    except Exception as e:  # noqa: BLE001
        log("quit message:", type(e).__name__, e)
    try:
        proc.wait(60)
    except subprocess.TimeoutExpired:
        proc.kill()
    log("exit code", proc.returncode)


def chrome(m, script, args=None):
    with m.using_context("chrome"):
        return m.execute_async_script(script, script_args=args or [], script_timeout=60000)


def orbis_pids():
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        "(Get-Process orbis -ErrorAction SilentlyContinue).Id"], capture_output=True, text=True)
    return {int(x) for x in r.stdout.split()}


def win_titles():
    """Visible top-level window titles of orbis.exe processes (Win32)."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    pids = orbis_pids()
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
]

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


def sample_tcp(conns):
    ps = ("$p = Get-Process orbis -ErrorAction SilentlyContinue | Select-Object -Expand Id; "
          "if ($p) { Get-NetTCPConnection -OwningProcess $p -ErrorAction SilentlyContinue | "
          "Where-Object { $_.RemoteAddress -notin '0.0.0.0','::','127.0.0.1','::1' } | "
          "ForEach-Object { '{0} {1} {2} {3}' -f $_.OwningProcess, $_.RemoteAddress, $_.RemotePort, $_.State } }")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 4:
            conns.add((parts[1], parts[2]))


def phase_default():
    before = tree_state()
    dump("b-before.json", before)
    proc = launch(None, 2828, headless=True, no_profile=True)
    m = connect(2828)
    time.sleep(20)
    info = chrome(m, "const d=arguments[arguments.length-1]; d({profD: Services.dirsvc.get('ProfD', Ci.nsIFile).path,"
                     " localD: Services.dirsvc.get('ProfLD', Ci.nsIFile).path,"
                     " defRoot: Services.dirsvc.get('DefProfRt', Ci.nsIFile).path});")
    dump("b-dirs.json", info)
    quit_browser(m, proc)
    time.sleep(3)
    after = tree_state()
    dump("b-after.json", after)
    log(json.dumps({"dirs": info, "before": before, "after": after}, indent=1))


def phase_idle():
    prof = os.path.join(PROFILES, "idle-" + time.strftime("%H%M%S"))
    dnslog = os.path.join(OUT, "dns.log")
    proc = launch(prof, 28282, headless=True,
                  extra_env={"MOZ_LOG": "timestamp,nsHostResolver:5", "MOZ_LOG_FILE": dnslog})
    conns = set()
    t0 = time.time()
    while time.time() - t0 < 180:
        sample_tcp(conns)
        time.sleep(4)
    dump("f-tcp.json", sorted(conns))
    m = connect(28282)
    res = run_checks(m, "idle")
    sample_tcp(conns)
    dump("f-tcp.json", sorted(conns))
    quit_browser(m, proc)
    log("profile:", prof)
    log(json.dumps({k: res.get(k) for k in ("policiesStatus", "ubo", "selectedFilterLists", "error")}, indent=1))


def phase_second():
    if not ARGS.extra:
        sys.exit("second: give the idle profile folder as EXTRA")
    proc = launch(ARGS.extra, 28282, headless=True)
    m = connect(28282)
    time.sleep(30)
    res = run_checks(m, "second")
    quit_browser(m, proc)
    log(json.dumps({k: res.get(k) for k in ("ubo", "selectedFilterLists", "uboStorageKeys", "error")}, indent=1))


def phase_ui():
    prof = os.path.join(PROFILES, "ui-" + time.strftime("%H%M%S"))
    proc = launch(prof, 28283, headless=False)
    m = connect(28283)
    time.sleep(8)
    out = {}
    with m.using_context("chrome"):
        out["windowTitle"] = m.title
        out["docTitle"] = m.execute_script("return document.title")
        out["brand"] = m.execute_script("""
          const b = Services.strings.createBundle('chrome://branding/locale/brand.properties');
          return {short: b.GetStringFromName('brandShortName'), full: b.GetStringFromName('brandFullName')};""")
        out["win32TitlesMain"] = win_titles()
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
        out["win32TitlesWithAbout"] = win_titles()
        dump("g-ui.json", out)
        m.execute_script("window.close()")
        time.sleep(1)
        m.switch_to_window(m.chrome_window_handles[0])
        out["win32Titles"] = win_titles()
    dump("g-ui.json", out)
    quit_browser(m, proc)
    log(json.dumps({k: v for k, v in out.items() if k != "aboutText"}, indent=1))


def phase_hosts():
    counts = collections.Counter()
    files = sorted(glob.glob(os.path.join(OUT, "dns.log*")))
    if not files:
        sys.exit("No dns.log* files in %s (run the idle phase first)" % OUT)
    for path in files:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                for host in re.findall(r"Resolving host \[([^\]]+)\]", line):
                    counts[host] += 1
    for host, n in sorted(counts.items()):
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
    {"default": phase_default, "idle": phase_idle, "second": phase_second, "ui": phase_ui,
     "hosts": phase_hosts, "quit": phase_quit}[ARGS.phase]()
