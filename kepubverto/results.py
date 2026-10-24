# kepubverto for calibre — the report window
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""One row per book: what happened to it, and why when it was not converted.

**Modeless**, so the library view behind it stays usable: *Show in library*
marks the books and filters the view to them, and the window stays open for
the next question. The action keeps the reference, closes the previous window
before opening a new one, and closes it when the library changes.

The report says what produced it (date, kepubverto, plugin, calibre, system)
on the line under the summary and at the top of what *Copy* puts on the
clipboard, because most early defects in a plugin are the plugin's, and the
version is the first thing anyone helping will ask for.
"""

from qt.core import (QAbstractItemView, QApplication, QDialog,
                     QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
                     QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from calibre_plugins.kepubverto.convert import OUTCOME_LABELS, OUTCOME_ORDER

COLUMNS = ('Book', 'Result', 'Detail')


class ResultsDialog(QDialog):

    def __init__(self, parent, report, show_books):
        QDialog.__init__(self, parent)
        self.report = report
        self.show_books = show_books
        self.setWindowTitle('kepubverto: conversion report')
        self.resize(820, 480)
        layout = QVBoxLayout(self)

        summary = QLabel(report.summary_line(), self)
        summary.setWordWrap(True)
        layout.addWidget(summary)
        conditions = QLabel(self.conditions_text(), self)
        conditions.setWordWrap(True)
        conditions.setStyleSheet('color: palette(mid);')
        layout.addWidget(conditions)
        if report.note:
            layout.addWidget(QLabel(report.note, self))

        self.table = QTableWidget(self)
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.fill()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        self.table.doubleClicked.connect(self.show_selected)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.show_button = QPushButton('Show in library', self)
        self.show_button.setToolTip(
            'Mark the selected books (or, with nothing selected, every book '
            'that was not converted cleanly) and show them in the library.')
        self.show_button.clicked.connect(self.show_selected)
        buttons.addWidget(self.show_button)
        self.copy_button = QPushButton('Copy', self)
        self.copy_button.setToolTip(
            'Copy the report as tab-separated text, with what produced it.')
        self.copy_button.clicked.connect(self.copy)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close.rejected.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def conditions_text(self):
        return ', '.join('%s %s' % pair for pair in self.report.conditions())

    def rows(self):
        """`(book_id, title, result, detail)` in report order."""
        return [(b.book_id, b.title, OUTCOME_LABELS.get(b.outcome, b.outcome),
                 b.detail) for b in self.report.sorted_books()]

    def fill(self):
        """Sorting stays off: the report order is meaningful (what needs a
        look first), and `setSortingEnabled(False)` would also have to be
        undone around every fill."""
        rows = self.rows()
        self.table.setRowCount(len(rows))
        self._ids = []
        for r, (book_id, title, result, detail) in enumerate(rows):
            self._ids.append(book_id)
            for c, text in enumerate((title, result, detail)):
                item = QTableWidgetItem(text or '')
                item.setToolTip(text or '')
                self.table.setItem(r, c, item)

    def selected_ids(self):
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        return [self._ids[r] for r in sorted(rows)]

    def show_selected(self, *_args):
        ids = self.selected_ids()
        label = 'the selected books'
        if not ids:
            not_clean = [o for o in OUTCOME_ORDER if o != 'converted']
            ids = sorted(self.report.ids(not_clean))
            label = 'not converted cleanly'
        if ids:
            self.show_books(ids, label)

    def text(self):
        """The report as text: the conditions, a header, one line per book."""
        lines = ['kepubverto conversion report',
                 self.report.summary_line(),
                 self.conditions_text(),
                 '',
                 '\t'.join(('book id',) + COLUMNS)]
        for book_id, title, result, detail in self.rows():
            lines.append('\t'.join(str(v).replace('\t', ' ').replace('\n', ' ')
                                   for v in (book_id, title, result, detail)))
        return '\n'.join(lines) + '\n'

    def copy(self):
        QApplication.clipboard().setText(self.text())
