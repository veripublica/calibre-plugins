#!/usr/bin/env python3
# kepubverto for calibre — stage the MobileRead attachment set
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Stage the two files to attach to the first post of the plugin's thread.

    python3 kepubverto/forum.py
        -> dist/kepubverto/forum/kepubverto_calibre_vX.Y.Z.zip
        -> dist/kepubverto/forum/SHA256SUMS.txt

Adapted from epubveri-plugins' calibre library plugin (`forum.py`).

**It stages the published release asset, not a local build**, so the thread
carries the same bytes and checksum file as the GitHub release. Downloading
what GitHub serves also catches a build of a tree that was never released and
a version whose release does not exist yet.

How calibre's plugin index reads a thread (epubveri-plugins, measured
2026-09-17): it takes the **first `.zip` attached to the thread's first
post**, reads the version from `PLUGIN_VERSION_TUPLE` in `__init__.py` with an
AST parse, and updates installed copies when the attachment's `Last-Modified`
changes. The filename reaches nobody (calibre stores it as `<thread>.zip`).

This script does not touch the forum. Attaching is manual.
"""

import hashlib
import importlib.util
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Loaded by path under its own name, as the tests do: `build` is a common
# module name, and calibre's interpreter already has one.
_spec = importlib.util.spec_from_file_location(
    "kepubverto_build", os.path.join(HERE, "build.py"))
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

FORUM = os.path.join(build.DIST, "forum")

#: The plugin's own thread in MobileRead's Plugins forum, posted with 0.1.0 on
#: 2026-10-24 ("[GUI Plugin] kepubverto").
THREAD = "375915"
THREAD_URL = ("https://www.mobileread.com/forums/showthread.php?t=%s" % THREAD
              if THREAD else None)

REPO = "veripublica/calibre-plugins"
TAG_PREFIX = "kepubverto-v"
ASSET = "kepubverto_calibre_v%s.zip"
SUMS = "SHA256SUMS.txt"

#: calibre imports nothing unless both are at the top of the archive.
REQUIRED_AT_ROOT = ("__init__.py", "plugin-import-name-kepubverto.txt")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(tag, name, target):
    url = "https://github.com/%s/releases/download/%s/%s" % (REPO, tag, name)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise SystemExit(
                "%s is not on release %s.\nCut the release before staging the "
                "forum attachment: the thread must carry what GitHub serves."
                % (name, tag))
        raise SystemExit("could not fetch %s: %s" % (url, err))
    with open(target, "wb") as handle:
        handle.write(data)
    return target


def checksum_for(sums_path, name):
    with open(sums_path, encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                return parts[0]
    raise SystemExit("%s does not name %s" % (SUMS, name))


def check_archive(path, expected_version):
    """Refuse an archive calibre could not install or would misread."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        missing = [n for n in REQUIRED_AT_ROOT if n not in names]
        if missing:
            raise SystemExit("%s is missing %s at the root of the archive"
                             % (os.path.basename(path), ", ".join(missing)))
        text = zf.read("__init__.py").decode("utf-8")
    match = build.VERSION_RE.search(text)
    got = [p.strip() for p in match.group(1).split(",")] if match else None
    if got != expected_version.split("."):
        raise SystemExit("the released archive declares %s, this tree "
                         "declares %s" % (".".join(got or ["?"]),
                                          expected_version))


def drift_from_source(released):
    """Members this tree would build differently from the release. Reported,
    not enforced: the attachment is the released artifact either way."""
    local = build.build()
    if sha256(local) == sha256(released):
        return []
    with zipfile.ZipFile(released) as a, zipfile.ZipFile(local) as b:
        names = sorted(set(a.namelist()) | set(b.namelist()))
        return [n for n in names
                if n not in a.namelist() or n not in b.namelist()
                or a.read(n) != b.read(n)]


def stage():
    version = build.version()
    tag = TAG_PREFIX + version
    name = ASSET % version

    shutil.rmtree(FORUM, ignore_errors=True)
    os.makedirs(FORUM)
    archive = download(tag, name, os.path.join(FORUM, name))
    sums = download(tag, SUMS, os.path.join(FORUM, SUMS))

    digest = sha256(archive)
    recorded = checksum_for(sums, name)
    if digest != recorded:
        raise SystemExit("the downloaded archive does not match %s on release "
                         "%s\n  recorded  %s\n  actual    %s"
                         % (SUMS, tag, recorded, digest))
    check_archive(archive, version)
    zips = [f for f in os.listdir(FORUM) if f.endswith(".zip")]
    if len(zips) != 1:
        raise SystemExit("expected exactly one zip to attach, found %d"
                         % len(zips))
    return version, tag, archive, sums, digest, drift_from_source(archive)


if __name__ == "__main__":
    version, tag, archive, sums, digest, drift = stage()
    rel = os.path.relpath(FORUM, ROOT)
    print("kepubverto for calibre %s (%s), verified against the release\n"
          % (version, tag))
    print("  %s/%s  (%.1f KB)" % (rel, os.path.basename(archive),
                                  os.path.getsize(archive) / 1024.0))
    print("  %s/%s" % (rel, os.path.basename(sums)))
    print("  sha256  %s\n" % digest)
    if THREAD_URL:
        print("Attach both to the FIRST post of %s" % THREAD_URL)
        print("  1. delete the zip already attached there first: the index")
        print("     takes the first zip on the page")
        print("  2. upload these two, then check the post shows one zip only")
        print("  3. the index re-scrapes on its own schedule, not immediately")
    else:
        print("There is no thread yet. Attach both to the first post of the")
        print("new thread in MobileRead's Plugins forum, then write its number")
        print("into THREAD in kepubverto/forum.py and ask a moderator to add")
        print("it to calibre's plugin index.")
    if drift:
        print("\nNote: this tree would build %d file(s) differently from the"
              % len(drift))
        print("release; the attachment is still the released artifact:")
        for member in drift:
            print("  - %s" % member)
    sys.exit(0)
