#!/usr/bin/env python3
# kepubverto for calibre — package this plugin
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Zip this folder the way calibre installs it.

    python3 kepubverto/build.py
        -> dist/kepubverto/kepubverto_calibre_vX.Y.Z.zip

**calibre wants the plugin's files at the top level of the zip.**
`__init__.py` and `plugin-import-name-kepubverto.txt` have to be at the root
of the archive, or calibre installs nothing. The import-name marker is the
plugin's whole claim on its name in calibre's loader table; losing it breaks
the install.

The archive's filename reaches nobody (calibre stores a downloaded plugin as
`<thread>.zip`), so it is free to say what it is for.
"""

import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist", "kepubverto")

VERSION_RE = re.compile(r"PLUGIN_VERSION_TUPLE\s*=\s*\(([^)]*)\)")

#: Everything in this folder that is not the plugin. `forum.py` once landed
#: inside a sibling's built zip because only `build.py` was named; anything
#: added beside this file that is a tool, not plugin code, goes here.
EXCLUDE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "build.py",
                                 "forum.py", "make_icon.py",
                                 "README.md", "CHANGELOG.md",
                                 "kepubverto", "kepubverto.exe", ".DS_Store")


def version():
    with open(os.path.join(HERE, "__init__.py"), encoding="utf-8") as handle:
        match = VERSION_RE.search(handle.read())
    if not match:
        raise SystemExit("__init__.py has no PLUGIN_VERSION_TUPLE")
    return ".".join(p.strip() for p in match.group(1).split(",") if p.strip())


def build():
    staging = os.path.join(DIST, ".staging")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(HERE, staging, ignore=EXCLUDE)
    shutil.copy2(os.path.join(ROOT, "LICENSE"), staging)

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "kepubverto_calibre_v%s.zip" % version())
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirs, files in os.walk(staging):
            dirs.sort()
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, staging).replace(os.sep, "/")
                # No wrapping folder: calibre reads __init__.py from the top.
                zf.write(full, rel)
    shutil.rmtree(staging, ignore_errors=True)
    return out


if __name__ == "__main__":
    path = build()
    print("%s  (%.1f KB)" % (os.path.relpath(path, ROOT),
                             os.path.getsize(path) / 1024.0))
    sys.exit(0)
