# kepubverto for calibre — saving KEPUBs as .kepub.epub
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Save books' KEPUBs to a folder, named `<title> - <authors>.kepub.epub`.

**`.kepub.epub` is kepubverto's name on purpose**, and the one a Kobo uses.
calibre stores the format as `KEPUB`, and so names the file in the library
`.kepub`. Its Kobo driver puts the `.epub` back when it sends the book
(`KOBO.filename_callback`, calibre 9.17), but calibre's own Save to disk does
not. This is the save that does (Baris, 2026-10-24).

The format stays `KEPUB` in the library: the Kobo driver only sends the
`kepub` format as a KEPUB, and calibre's viewer and conversion know it by
that name.
"""

import os

from calibre_plugins.kepubverto.convert import TARGET_FORMAT

EXTENSION = '.kepub.epub'

#: Long titles are cut so the whole path stays well inside Windows' limits.
MAX_STEM = 150


def file_stem(title, authors):
    """`<title> - <authors>`, safe as a file name on every platform."""
    from calibre.utils.filenames import sanitize_file_name
    title = (title or '').strip() or 'Unknown'
    names = [a for a in (authors or ()) if a and a.strip()]
    stem = '%s - %s' % (title, ' & '.join(names)) if names else title
    stem = sanitize_file_name(stem).strip(' .')
    return (stem[:MAX_STEM].rstrip(' .')) or 'book'


def free_path(folder, stem):
    """A path in `folder` that does not exist yet. Nothing is overwritten:
    a second save of the same book becomes `<stem> (2).kepub.epub`."""
    path = os.path.join(folder, stem + EXTENSION)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, '%s (%d)%s' % (stem, n, EXTENSION))
        n += 1
    return path


def save_kepubs(db, book_ids, folder):
    """Copy each book's KEPUB into `folder`.

    `db` is calibre's `new_api`. Returns `(saved, without, failed)`: the paths
    written, the books that have no KEPUB, and `(book_id, title, error)` for
    each copy that failed.
    """
    saved, without, failed = [], [], []
    for book_id in book_ids:
        title = db.field_for('title', book_id)
        if not db.has_format(book_id, TARGET_FORMAT):
            without.append(book_id)
            continue
        path = free_path(folder, file_stem(title,
                                           db.field_for('authors', book_id)))
        try:
            db.copy_format_to(book_id, TARGET_FORMAT, path)
        except Exception as exc:                        # noqa: BLE001
            # No half-written file left behind under a name that looks done.
            try:
                os.remove(path)
            except OSError:
                pass
            failed.append((book_id, title, str(exc)))
            continue
        saved.append(path)
    return saved, without, failed
