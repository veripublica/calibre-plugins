# kepubverto for calibre — preferences
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Settings: the conversion options, what to do with an existing KEPUB, how
many books at once, and the converter's updates.

The page follows the family's calibre lesson: short sections, one dimmed line
each, the explanation in tooltips. calibre wraps the page in a `QScrollArea`,
so anything wide buys a horizontal scrollbar instead of a wider window.

**Only options a kepubverto release has are offered** (agreed with kepubverto,
2026-10-24), and the plugin refuses a binary older than the release that
introduced them (`MIN_CONVERTER_VERSION`).
"""

from calibre.utils.config import JSONConfig
from qt.core import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                     QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget)

#: The file is named after the plugin: `plugins/kepubverto.json`.
prefs = JSONConfig('plugins/kepubverto')

prefs.defaults['autoupdate'] = True
#: '' (the book decides: `--hyphens` is not passed), 'auto' or 'none'.
prefs.defaults['hyphens'] = ''
#: One `--css` value. Empty means none.
prefs.defaults['css'] = ''
#: Whether a book that already has a KEPUB gets a new one. Off by default: a
#: KEPUB already in the library may be one the user made on purpose, with
#: other options or another tool, and replacing it silently loses it.
prefs.defaults['replace_existing'] = False
#: How many books are converted at once. 0 means "work it out".
prefs.defaults['workers'] = 0

HYPHEN_CHOICES = (
    ('', 'As the book says'),
    ('auto', 'On'),
    ('none', 'Off'),
)

_ON_VALUES = frozenset(['yes', 'true', 'on', '1', 'y'])


def as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _ON_VALUES


def hyphens():
    """The `--hyphens` value to pass, or None for "the book decides"."""
    value = prefs.get('hyphens') or ''
    return value if value in ('auto', 'none') else None


def css_values():
    """The `--css` values to pass: one, or none."""
    value = prefs.get('css') or ''
    return (value,) if value.strip() else ()


def replace_existing():
    return as_bool(prefs.get('replace_existing'), False)


def workers(jobs=()):
    """The worker count: the user's, clamped, or one computed for them."""
    from calibre_plugins.kepubverto.convert import (recommended_workers,
                                                    worker_cap)
    try:
        chosen = int(prefs.get('workers') or 0)
    except (TypeError, ValueError):
        chosen = 0
    if chosen <= 0:
        return recommended_workers(jobs)
    return max(1, min(chosen, worker_cap()))


class ConfigWidget(QWidget):
    """Preferences / Plugins / Customize, and Settings in the plugin's menu."""

    #: How narrow a wrapped caption may get inside calibre's scroll area.
    NOTE_WIDTH = 320

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._section(layout, 'Conversion',
                      'Added to every converted document of every book.')
        row = QHBoxLayout()
        label = QLabel('Hyphenation:', self)
        row.addWidget(label)
        self.hyphens = QComboBox(self)
        for value, text in HYPHEN_CHOICES:
            self.hyphens.addItem(text, value)
        index = self.hyphens.findData(prefs.get('hyphens') or '')
        self.hyphens.setCurrentIndex(max(0, index))
        explain = ('As the book says: no hyphenation CSS is added. On: the '
                   "reader's dictionary for the book's language breaks the "
                   'words; headings, table cells and the book\'s own '
                   'per-element choices are left alone. Off: hyphenation is '
                   'turned off, even where the book turns it on.')
        for widget in (label, self.hyphens):
            widget.setToolTip(explain)
        row.addWidget(self.hyphens)
        row.addStretch(1)
        layout.addLayout(row)

        css_label = QLabel('Your own CSS, after kepubverto\'s rules:', self)
        layout.addWidget(css_label)
        self.css = QPlainTextEdit(self)
        self.css.setPlaceholderText('p { text-indent: 1.5em; margin: 0 }')
        self.css.setPlainText(prefs.get('css') or '')
        # A few lines tall: the page has to stay shorter than the dialog.
        self.css.setFixedHeight(self.css.fontMetrics().lineSpacing() * 4 + 12)
        css_explain = ('Checked by kepubverto before each book is converted. '
                       'It is refused if it refers to a file, has @font-face, '
                       'or would add a finding epubveri reports; the book is '
                       'then left without a KEPUB and the report shows '
                       "kepubverto's reason.")
        for widget in (css_label, self.css):
            widget.setToolTip(css_explain)
        layout.addWidget(self.css)

        layout.addSpacing(10)
        self._section(layout, 'Books that already have a KEPUB',
                      'Left as they are unless you choose otherwise.')
        self.replace_existing = self._check(
            'Replace an existing KEPUB',
            'A KEPUB already in the library may have been made on purpose, '
            'with other options or another tool. When this is off, such a '
            'book is skipped and the report says so.')
        self.replace_existing.setChecked(replace_existing())
        layout.addWidget(self.replace_existing)

        layout.addSpacing(10)
        self._section(layout, 'Converting',
                      'Two cores are kept for the rest of the system.')
        from calibre_plugins.kepubverto.convert import (recommended_workers,
                                                        worker_cap)
        cap = worker_cap()
        row = QHBoxLayout()
        label = QLabel('Books converted at the same time:', self)
        row.addWidget(label)
        self.workers = QSpinBox(self)
        self.workers.setRange(0, cap)
        automatic = 'Automatic (%d)' % recommended_workers()
        self.workers.setSpecialValueText(automatic)
        # A spin box sizes itself to its number range, not to its special
        # value text; measured off its own font.
        self.workers.setMinimumWidth(
            self.workers.fontMetrics().horizontalAdvance(automatic)
            + self.workers.fontMetrics().height() * 2)
        try:
            self.workers.setValue(min(cap, max(0, int(prefs.get('workers') or 0))))
        except (TypeError, ValueError):
            self.workers.setValue(0)
        row.addWidget(self.workers)
        row.addStretch(1)
        layout.addLayout(row)
        explain = ('Automatic is %(auto)d on this machine. The maximum is '
                   '%(cap)d: two cores are kept for the rest of the system, '
                   'including calibre itself.') % {
                       'auto': recommended_workers(), 'cap': cap}
        for widget in (label, self.workers):
            widget.setToolTip(explain)

        layout.addSpacing(10)
        self._section(layout, 'The converter',
                      'Downloaded on first use, checked against the release '
                      'checksums.')
        self.autoupdate = self._check(
            'Check for a newer kepubverto',
            'At most once an hour, and never during a conversion. Every '
            'download is verified against the release\'s SHA256SUMS.txt, and '
            'the binary is checked again before every run.')
        self.autoupdate.setChecked(as_bool(prefs.get('autoupdate')))
        layout.addWidget(self.autoupdate)

        layout.addStretch(1)

    def _section(self, layout, text, note):
        """A bold title and one dimmed line, not a `QGroupBox`."""
        heading = QLabel('<b>%s</b>' % text, self)
        caption = QLabel(note, self)
        caption.setWordWrap(True)
        caption.setMinimumWidth(self.NOTE_WIDTH)
        font = caption.font()
        font.setPointSizeF(max(9.0, font.pointSizeF() - 2.0))
        caption.setFont(font)
        caption.setStyleSheet('color: palette(mid);')
        layout.addWidget(heading)
        layout.addWidget(caption)

    def _check(self, text, explanation):
        """A short checkbox label (it does not wrap), the rest in a tooltip."""
        box = QCheckBox(text, self)
        box.setToolTip(explanation)
        return box

    def save_settings(self):
        prefs['hyphens'] = self.hyphens.currentData() or ''
        prefs['css'] = self.css.toPlainText()
        prefs['replace_existing'] = self.replace_existing.isChecked()
        prefs['workers'] = self.workers.value()
        prefs['autoupdate'] = self.autoupdate.isChecked()
