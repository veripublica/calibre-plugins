# kepubverto for calibre — running the kepubverto binary
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Invoke kepubverto on one book and hand back a parsed envelope.

The output always goes to a path the caller chose inside a fresh temporary
folder, so the "exists; use -f" refusal can never happen and `-f` is never
passed. The book in the library is only ever read.
"""

import os
import subprocess

from .envelope import parse_envelope

#: A book that takes longer than this is not going to finish. A 34-document
#: novel converts in well under a second; the margin is for a large
#: illustrated book on a slow disk.
DEFAULT_TIMEOUT = 300

#: The values `--hyphens` takes. Not passing it at all is the third choice:
#: the book decides.
HYPHENS = ("auto", "none")


class ConverterNotFound(Exception):
    """No usable binary. The caller offers to fetch one."""


def _no_window_kwargs():
    """Keep a console window from flashing on Windows for every book."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def command(binary, epub_path, output_path, hyphens=None, css=()):
    """The command line for one book. Separate so the tests can read it."""
    cmd = [binary, "-i", epub_path, "-o", output_path, "--format", "json"]
    if hyphens in HYPHENS:
        cmd.extend(["--hyphens", hyphens])
    for value in css or ():
        # One `--css` per value; kepubverto checks each one on its own and
        # names it by its position in a refusal ("--css value 1").
        if value and value.strip():
            cmd.extend(["--css", value])
    return cmd


def run_kepubverto(binary, epub_path, output_path, hyphens=None, css=(),
                   timeout=DEFAULT_TIMEOUT):
    """Convert one `.epub` to `output_path` and return an `Envelope`.

    Raises `ConverterNotFound` if the binary is missing, and `EnvelopeError`
    if stdout held no envelope (a refusal), whose message is kepubverto's
    stderr as it is.
    """
    if not binary or not os.path.isfile(binary):
        raise ConverterNotFound(binary or "(no path)")
    proc = subprocess.run(
        command(binary, epub_path, output_path, hyphens, css),
        capture_output=True, timeout=timeout, **_no_window_kwargs())
    return parse_envelope(proc.stdout, proc.stderr, proc.returncode)


def binary_version(binary, timeout=15):
    """`kepubverto -V` output (`kepubverto 0.3.0+1ce1e8c`), or None."""
    try:
        proc = subprocess.run([binary, "-V"], capture_output=True,
                              timeout=timeout, **_no_window_kwargs())
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or b"").decode("utf-8", "replace").strip()
    return text or None
