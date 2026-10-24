# kepubverto for calibre — getting a verified binary
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Where the kepubverto binary lives, and how it stays the one verified.

Adapted from epubveri-plugins' calibre library plugin (`install.py`).

**The binary is this plugin's own copy**, in `<config>/plugins/kepubverto-data/`.
calibre never unpacks a plugin, so there is no plugin folder to write into,
and Windows will not replace a running executable: a library conversion holds
the binary open for its whole run, and nothing else may update it meanwhile.

**The install record lives beside the binary** (`install.json`) rather than in
the preferences. It describes the file, so delete the folder and the two go
together.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from calibre.constants import config_dir

from calibre_plugins.kepubverto import MIN_CONVERTER_VERSION
from calibre_plugins.kepubverto.client import binary as bin_mod
from calibre_plugins.kepubverto.client import runner

#: How long a recorded update check stays good for.
UPDATE_INTERVAL = timedelta(hours=1)
STALE_AFTER = timedelta(days=30)
CHECK_TIMEOUT = 5

RECORD_NAME = 'install.json'

#: Checked free on 2026-10-24. Not `kepubverto`, so that the name of the
#: plugin's prefs file (`kepubverto.json`) and of this folder can never be
#: mistaken for one another, and so a file another tool leaves under that name
#: cannot be in the way.
DATA_DIR_NAME = 'kepubverto-data'


class InstallPathError(Exception):
    """The folder cannot be created because something else has the name."""


def _now():
    return datetime.now(timezone.utc)


def _stamp():
    return int(_now().timestamp())


def since(value):
    """How long ago a recorded stamp was, or None."""
    if value in (None, ''):
        return None
    try:
        when = datetime.fromtimestamp(float(value), timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    return _now() - when


def data_dir(create=True):
    """Where the binary lives. `create=False` only asks."""
    path = os.path.join(config_dir, 'plugins', DATA_DIR_NAME)
    if os.path.isdir(path) or not create:
        return path
    if os.path.exists(path) or os.path.islink(path):
        # Say which path is occupied rather than blaming the network.
        raise InstallPathError(
            'kepubverto keeps its converter in\n%s\nand that name is already '
            'taken by something which is not a folder. Rename or remove it '
            'and try again. Nothing was installed and nothing was changed.'
            % path)
    os.makedirs(path, exist_ok=True)
    return path


def binary_path():
    return os.path.join(data_dir(), bin_mod.binary_filename())


def _record_path():
    return os.path.join(data_dir(), RECORD_NAME)


def read_record():
    """The install record, or an empty dict. Read from disk every time."""
    try:
        with open(_record_path(), encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_record(**fields):
    """Merge `fields` into the record, written whole and replaced."""
    data = read_record()
    data.update(fields)
    path = _record_path()
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        # A record we cannot write costs an extra update check, nothing more.
        try:
            os.remove(tmp)
        except OSError:
            pass
    return data


def _remember(archive_sha, binary_sha):
    stamp = _stamp()
    write_record(installed_sha256=archive_sha, binary_sha256=binary_sha,
                 last_update_check=stamp, last_update_success=stamp)


def integrity_failure(path):
    """Is the binary on disk still the one the release vouched for?

    Verifying at download time proves what arrived, not what runs. A missing
    recorded hash is trusted once and recorded.
    """
    stored = read_record().get('binary_sha256')
    actual = bin_mod.sha256_of(path)
    if not stored:
        write_record(binary_sha256=actual)
        return None
    if actual == stored:
        return None
    return ('the kepubverto binary has changed since it was verified '
            '(expected %s, found %s). It was not run. Delete\n%s\nand try '
            'again to reinstall a verified copy.'
            % (stored[:16], actual[:16], path))


def stale_note(allowed=True):
    """One quiet line when the binary has not been checked for a month."""
    age = since(read_record().get('last_update_success'))
    if age is None or age < STALE_AFTER:
        return None
    if not allowed:
        return ('this kepubverto is %d days old; automatic updates are off'
                % age.days)
    return ('this kepubverto is %d days old; no update check has succeeded '
            'since' % age.days)


def install_failure(exc):
    """A sentence a calibre user can act on. Anything that is not about the
    network is recognised before the last line, which names the network."""
    if isinstance(exc, InstallPathError):
        return str(exc)
    if isinstance(exc, bin_mod.DownloadError):
        return 'kepubverto could not be installed: %s' % exc
    return ('kepubverto could not be downloaded. The first run needs an '
            'internet connection; after that the plugin works offline. (%s)'
            % exc)


def _fmt(version):
    return '.'.join(str(n) for n in version) if version else None


def update_note(before, after):
    old = bin_mod.parse_version(before)
    new = bin_mod.parse_version(after)
    if old and new and old != new:
        return 'updated kepubverto %s to %s' % (_fmt(old), _fmt(new))
    if new:
        return 'reinstalled kepubverto %s' % _fmt(new)
    return 'updated kepubverto'


def version_failure(path):
    """A sentence if the binary is older than this plugin needs, else None.

    `releases/latest` is always new enough, so this only fires for a binary
    that automatic updates were turned off on.
    """
    found = bin_mod.parse_version(runner.binary_version(path))
    if found is None:
        return ('kepubverto at\n%s\ndid not report its version, so it was '
                'not run.' % path)
    if found < MIN_CONVERTER_VERSION:
        return ('this plugin needs kepubverto %s or newer, and the copy it '
                'has is %s. Turn on "Check for a newer kepubverto" in the '
                'settings, or delete\n%s\nand try again.'
                % (_fmt(MIN_CONVERTER_VERSION), _fmt(found), path))
    return None


def ensure_binary(autoupdate=True):
    """The binary to use, installing or updating it as needed.

    Returns `(path, note)`. `path` is None when the binary must not be run,
    and `note` says why. Called once per conversion run, on the GUI side, so a
    long run can never have its executable replaced halfway through.
    """
    path = binary_path()

    if not os.path.isfile(path):
        installed, archive_sha, binary_sha = bin_mod.download_binary(data_dir())
        _remember(archive_sha, binary_sha)
        return installed, 'installed kepubverto'

    tampered = integrity_failure(path)
    if tampered:
        return None, tampered

    note = None
    if not autoupdate:
        note = stale_note(allowed=False)
    else:
        age = since(read_record().get('last_update_check'))
        if age is None or age >= UPDATE_INTERVAL:
            write_record(last_update_check=_stamp())
            note = stale_note()
            try:
                sums = bin_mod.latest_checksums(timeout=CHECK_TIMEOUT)
                wanted = sums.get(bin_mod.asset_name())
                write_record(last_update_success=_stamp())
                note = None
                if wanted and wanted != read_record().get('installed_sha256'):
                    before = runner.binary_version(path) or ''
                    _path, archive_sha, binary_sha = bin_mod.download_binary(
                        data_dir(), expected=wanted)
                    _remember(archive_sha, binary_sha)
                    note = update_note(before,
                                       runner.binary_version(path) or '')
            except Exception:                           # noqa: BLE001
                # Offline, rate-limited, a changed release: none of it is a
                # reason to refuse to convert with the copy we have.
                pass

    too_old = version_failure(path)
    if too_old:
        return None, too_old
    return path, note
