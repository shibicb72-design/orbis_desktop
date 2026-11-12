# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Check that every option in the Orbis mozconfig exists in the pinned Firefox source.

    python -I scripts/check-mozconfig.py [--source DIR] [--mozconfig FILE]

--source is the Firefox checkout (default %USERPROFILE%\\orbis_desktop_src\\firefox). The script reads the
*.configure files and the top-level moz.configure there, collects every option(...) declaration (its flag name
and its env= name), and fails (exit code 1) if the mozconfig uses:

- an `ac_add_options --enable-X/--disable-X/--with-X/--without-X` whose X is not declared, or an
  `ac_add_options --X=value` (such as --target) whose --X is not declared;
- an `export VAR=...` or `ac_add_options VAR=...` whose VAR is not declared as env= of an option;
- `--enable-official-branding` (Mozilla's trademarks), or `--with-branding` pointing anywhere but
  browser/branding/orbis;
- `MOZ_REQUIRE_SIGNING` set to anything but 1.

It also prints, for each option, the file and line that declares it. It does not run configure.
"""

import argparse
import os
import re
import sys


def declared_options(source):
    """Returns ({flag-name: where}, {env-name: where}) from option(...) calls in the configure files."""
    flags, envs = {}, {}
    files = [os.path.join(source, "moz.configure")]
    for top in ("build", "browser", "toolkit", "js", "js/moz.configure", "python", "taskcluster", "mobile"):
        root = os.path.join(source, top)
        if os.path.isfile(root):
            files.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "test", "tests")]
            for fn in filenames:
                if fn.endswith(".configure"):
                    files.append(os.path.join(dirpath, fn))
    call = re.compile(r"\b(?:option|project_flag|confvar)\(\s*(.*?)\)", re.S)
    for path in sorted(set(files)):
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        rel = os.path.relpath(path, source).replace("\\", "/")
        for m in call.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            body = m.group(1)
            fm = re.match(r"\s*\"--(?:enable|disable|with|without)-([a-z0-9-]+)\"", body)
            if fm:
                flags.setdefault(fm.group(1), "%s:%d" % (rel, line))
            else:
                pm = re.match(r"\s*\"--([a-z0-9-]+)\"", body)
                if pm:
                    flags.setdefault("--" + pm.group(1), "%s:%d" % (rel, line))
            for em in re.finditer(r"env=\"([A-Z0-9_]+)\"", body):
                envs.setdefault(em.group(1), "%s:%d" % (rel, line))
            em = re.match(r"\s*\"([A-Z][A-Z0-9_]+)\"", body)
            if em:
                envs.setdefault(em.group(1), "%s:%d" % (rel, line))
    return flags, envs


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", default=os.path.join(os.environ.get("USERPROFILE", ""),
                                                     "orbis_desktop_src", "firefox"))
    ap.add_argument("--mozconfig", default=os.path.join(repo, "mozconfig"))
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.source, "moz.configure")):
        print("FAILED: no Firefox checkout at %s" % args.source)
        return 1
    flags, envs = declared_options(args.source)
    problems = []
    with open(args.mozconfig, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    for n, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"ac_add_options\s+--(enable|disable|with|without)-([a-z0-9-]+)(?:=(.*))?$", line)
        if m:
            name, value = m.group(2), m.group(3)
            where = flags.get(name)
            print("%-48s %s" % (line, where or "NOT DECLARED"))
            if not where:
                problems.append("line %d: --%s-%s is not declared in the source" % (n, m.group(1), name))
            if name == "official-branding" and m.group(1) == "enable":
                problems.append("line %d: official branding uses Mozilla's trademarks" % n)
            if name == "branding" and value != "browser/branding/orbis":
                problems.append("line %d: --with-branding must be browser/branding/orbis" % n)
            continue
        m = re.match(r"ac_add_options\s+--([a-z0-9-]+)=(.*)$", line)
        if m and not re.match(r"(enable|disable|with|without)-", m.group(1)):
            where = flags.get("--" + m.group(1))
            print("%-48s %s" % (line, where or "NOT DECLARED"))
            if not where:
                problems.append("line %d: --%s is not declared in the source" % (n, m.group(1)))
            continue
        m = re.match(r"(?:export|ac_add_options)\s+([A-Z][A-Z0-9_]*)=(.*)$", line)
        if m:
            name, value = m.group(1), m.group(2)
            where = envs.get(name)
            print("%-48s %s" % (line, where or "NOT DECLARED"))
            if not where:
                problems.append("line %d: %s is not an option in the source" % (n, name))
            if name == "MOZ_REQUIRE_SIGNING" and value != "1":
                problems.append("line %d: MOZ_REQUIRE_SIGNING must stay 1" % n)
            continue
        if re.match(r"mk_add_options\s+MOZ_OBJDIR=", line):
            print("%-48s (make option)" % line)
            continue
        problems.append("line %d: not understood: %s" % (n, line))

    if problems:
        for p in problems:
            print("FAIL: " + p)
        print("FAILED: %d problem(s)" % len(problems))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
