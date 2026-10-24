# kepubverto for calibre — finding, fetching and verifying the kepubverto binary
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Get a trustworthy kepubverto binary onto the user's machine.

**No binary is shipped inside the plugin zip, and that is a licence decision
as much as a size one.** kepubverto is AGPL-3.0-only OR commercial; this plugin
is GPL-3.0-only. The plugin only runs the binary as a subprocess and the
user's own machine fetches it from the project's releases, so a plugin package
distributes no AGPL code at all.

**Every download is verified against `SHA256SUMS.txt`** before it is
extracted, let alone run.

The release-asset layout is kepubverto's contract (its note of 2026-10-24):
`kepubverto-<target>.tar.gz` (Linux, macOS) or `.zip` (Windows) for eight
targets, plus `SHA256SUMS.txt` in `sha256sum` format, from
`releases/latest/download/`. Inside each archive is one folder,
`kepubverto-<target>/`, holding the binary, the licences and a README. The
binary is searched for by name rather than assumed at a path.
"""

import hashlib
import os
import platform
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile
from urllib.request import Request, urlopen

REPO = "veripublica/kepubverto"
CHECKSUMS_NAME = "SHA256SUMS.txt"

#: GitHub serves the newest release's assets from a stable path, so nothing
#: here needs the API, which is rate-limited for unauthenticated callers.
LATEST_DOWNLOAD = "https://github.com/%s/releases/latest/download/%%s" % REPO

#: Every network call gets one; Python's default is "wait forever".
NETWORK_TIMEOUT = 30

#: Release assets are named `kepubverto-<rust target triple>.<ext>`. The
#: mapping is exact, not fuzzy: a wrong guess downloads a binary that will not
#: run.
#:
#: `gnu` rather than `musl` for Linux, the same choice as the family's other
#: calibre plugins: kepubverto builds and keeps both, the musl builds matter
#: for a container, and a desktop running calibre is already a glibc system.
_TARGETS = {
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Windows", "ARM64"): "aarch64-pc-windows-msvc",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("Linux", "arm64"): "aarch64-unknown-linux-gnu",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
}


class DownloadError(Exception):
    pass


def binary_filename():
    return "kepubverto.exe" if platform.system() == "Windows" else "kepubverto"


def target_triple():
    """The release target for this machine, or None if none is built."""
    return _TARGETS.get((platform.system(), platform.machine()))


def asset_name(triple=None):
    triple = triple or target_triple()
    if triple is None:
        return None
    ext = ".zip" if "windows" in triple else ".tar.gz"
    return "kepubverto-%s%s" % (triple, ext)


def _get(url, timeout=NETWORK_TIMEOUT):
    request = Request(url, headers={
        # GitHub answers 403 without a User-Agent.
        "User-Agent": "calibre-plugins/kepubverto",
    })
    with urlopen(request, timeout=timeout) as response:
        return response.read()


_SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(\S+)\s*$")


def parse_checksums(text):
    """`{asset name: sha256}` from `sha256sum` output. Matched on the exact
    asset name: a looser match would accept another platform's hash."""
    sums = {}
    for line in text.splitlines():
        match = _SUM_LINE.match(line)
        if match:
            sums[os.path.basename(match.group(2))] = match.group(1).lower()
    return sums


def latest_checksums(timeout=NETWORK_TIMEOUT):
    """`{asset name: sha256}` for the newest release.

    **This is the update check.** Comparing checksums rather than version
    numbers needs no `kepubverto -V` process, and also catches an archive
    re-uploaded under the same tag.
    """
    text = _get(LATEST_DOWNLOAD % CHECKSUMS_NAME, timeout)
    return parse_checksums(text.decode("utf-8", "replace"))


def sha256_of(path):
    """SHA-256 of a file; cheap enough to do before every run."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_version(text):
    """`"kepubverto 0.3.0+1ce1e8c"` or `"v0.3.0"` -> `(0, 3, 0)`.

    Build metadata after `+` is dropped: `0.3.0+1ce1e8c` and `0.3.0` are the
    same release.
    """
    if not text:
        return None
    token = text.strip().split()[-1].lstrip("vV").split("+")[0]
    try:
        return tuple(int(p) for p in token.split(".")[:3])
    except ValueError:
        return None


def _safe_extract_tar(tf, dest):
    """Extract `tf` into `dest`, refusing any member that would land outside.

    The checksum file comes from the same release as the archive, so a
    compromised release passes that check; a crafted tar could then write
    through `../`, an absolute path or a link before anything is run. Python's
    `data` filter refuses all three, and older interpreters get the same
    refusals by hand.
    """
    if hasattr(tarfile, "data_filter"):
        tf.extractall(dest, filter="data")
        return
    root = os.path.realpath(dest)
    for member in tf.getmembers():
        target = os.path.realpath(os.path.join(dest, member.name))
        if not (member.isfile() or member.isdir()) or (
                target != root and not target.startswith(root + os.sep)):
            raise DownloadError(
                "refusing archive member %r: it is not a plain file inside "
                "the extraction directory. Nothing was installed." % member.name)
    tf.extractall(dest)


def _safe_extract_zip(zf, dest):
    """The zip counterpart: no member may resolve outside `dest`."""
    root = os.path.realpath(dest)
    for name in zf.namelist():
        target = os.path.realpath(os.path.join(dest, name))
        if target != root and not target.startswith(root + os.sep):
            raise DownloadError(
                "refusing archive member %r: it would land outside the "
                "extraction directory. Nothing was installed." % name)
    zf.extractall(dest)


def download_binary(destdir, expected=None, timeout=NETWORK_TIMEOUT):
    """Fetch the newest archive, verify it, extract the binary into `destdir`.

    Returns `(path, archive_sha256, binary_sha256)`. The first hash is what
    the next update check compares against; the second is what every run
    compares the file on disk against.

    Raises `DownloadError` with a sentence fit to show a user.
    """
    name = asset_name()
    if name is None:
        raise DownloadError(
            "there is no kepubverto build for this platform (%s %s)"
            % (platform.system(), platform.machine()))

    if expected is None:
        expected = latest_checksums(timeout).get(name)
        if expected is None:
            raise DownloadError(
                "%s does not list %s, so the archive is not one the release "
                "vouches for" % (CHECKSUMS_NAME, name))

    tmpdir = tempfile.mkdtemp(prefix="kepubverto-dl-")
    try:
        archive = os.path.join(tmpdir, name)
        with open(archive, "wb") as handle:
            handle.write(_get(LATEST_DOWNLOAD % name, timeout))

        actual = sha256_of(archive)
        if actual != expected:
            raise DownloadError(
                "checksum mismatch for %s: the release lists %s and the "
                "downloaded file is %s. Nothing was installed."
                % (name, expected[:16], actual[:16]))

        binary = binary_filename()
        extracted = os.path.join(tmpdir, "x")
        os.makedirs(extracted)
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                _safe_extract_zip(zf, extracted)
        else:
            with tarfile.open(archive) as tf:
                _safe_extract_tar(tf, extracted)

        found = None
        for root, _dirs, files in os.walk(extracted):
            if binary in files:
                found = os.path.join(root, binary)
                break
        if found is None:
            raise DownloadError("%s contained no %s" % (name, binary))

        os.makedirs(destdir, exist_ok=True)
        target = os.path.join(destdir, binary)
        shutil.copy2(found, target)
        mode = os.stat(target).st_mode
        os.chmod(target, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return target, expected, sha256_of(target)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
