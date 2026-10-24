# kepubverto for calibre — parsing kepubverto's JSON envelope
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""The `--format json` envelope, as kepubverto 0.3.0 documents it.

The envelope is the family's (conventions FORMATS.md); what is kepubverto's
own is the input's `summary` and the meaning of its items:

  * `summary` counts the book's content documents by outcome: `documents`,
    `converted`, `already_converted`, `nothing_to_do`, `left_alone`, and the
    `spans` added.
  * Each document **left as it was** is one item, with its path as `location`
    and the reason as `message`. A document left alone is copied byte for
    byte, so the KEPUB is never worse than the EPUB it came from.
  * `output` names the book written.

**Parse stdout first, whatever the exit code.** Exit 2 carries an envelope
when the book could not be read or written (`inputs[0].status: "error"`).
Only a refusal (a `--css` value, an output that exists) and a usage error
print nothing on stdout, and then stderr is the explanation.
"""

import json


class EnvelopeError(Exception):
    """stdout held no envelope: kepubverto refused, or did not start. The
    message is its stderr, which is written for a person."""


class Finding:
    """One item out of `inputs[].items`: a document left as it was."""

    __slots__ = ("code", "severity", "location", "message")

    def __init__(self, item):
        self.code = item.get("code", "")
        self.severity = item.get("severity", "error")
        # A container-relative path, not a basename.
        self.location = item.get("location")
        self.message = item.get("message", "")

    def __repr__(self):
        return "<Finding %s %s %s>" % (self.severity, self.code,
                                       self.location or "(no file)")


class Envelope:
    """One `--format json` run. One book per run, so `inputs[0]` is the book."""

    def __init__(self, doc):
        #: The envelope exactly as kepubverto produced it. Nothing here reads
        #: it; it is kept for a report a user may want to pass on.
        self.doc = doc
        self.tool_version = doc.get("tool_version", "")
        self.status = doc.get("status", "")
        inputs = doc.get("inputs") or [{}]
        book = inputs[0]
        self.input_status = book.get("status", "")
        self.error = book.get("error")
        self.output = book.get("output")
        self.summary = book.get("summary") or {}
        self.findings = [Finding(i) for i in (book.get("items") or [])]

    @property
    def version(self):
        """Without build metadata: `0.3.0+1ce1e8c` -> `0.3.0`."""
        return self.tool_version.split("+")[0]

    def count(self, key):
        try:
            return int(self.summary.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def could_not_convert(self):
        """The book could not be read, or could not be written."""
        return self.input_status == "error"

    @property
    def already_kepub(self):
        """The input was already a KEPUB: nothing converted, and documents
        that already carry Kobo's markup. kepubverto recognises its own
        output, kepubify's and calibre's the same way, by the `koboSpan`
        markup. Measured on 0.3.0: a second run gives `converted: 0`,
        `already_converted: 32`, and an output byte-identical to the input."""
        return (not self.could_not_convert
                and self.count("converted") == 0
                and self.count("already_converted") > 0)


def parse_envelope(stdout, stderr=b"", returncode=0):
    """Turn one kepubverto run into an `Envelope`, or raise `EnvelopeError`
    with kepubverto's own words when there is no envelope.

    stdout is decoded leniently on purpose: a path in it can carry anything,
    and a decode error would tell the user nothing about the book.
    """
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    try:
        doc = json.loads(stdout)
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        raise EnvelopeError(
            stderr.strip()
            or "kepubverto exited with %s and produced no output" % returncode)
    return Envelope(doc)
