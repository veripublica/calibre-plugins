# kepubverto for calibre — client for the kepubverto converter
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""This plugin's client for the kepubverto binary.

Taken from epubveri-plugins' calibre library plugin (`client/`, at 1a09f2b)
and adapted to kepubverto's own contract: its release assets, its envelope
summary and its exit codes. The structure and the reasoning are the same.

It talks to kepubverto as a **subprocess over its documented JSON envelope**,
and never links it. That keeps the licences apart (kepubverto is
AGPL-3.0-only OR commercial; this plugin is GPL-3.0-only), and it is why no
kepubverto binary is shipped inside the plugin zip: the user's machine fetches
it from the project's own releases and verifies it.
"""

from .envelope import Envelope, Finding, EnvelopeError, parse_envelope
from .runner import ConverterNotFound, run_kepubverto

__all__ = [
    "Envelope",
    "Finding",
    "EnvelopeError",
    "parse_envelope",
    "ConverterNotFound",
    "run_kepubverto",
]
