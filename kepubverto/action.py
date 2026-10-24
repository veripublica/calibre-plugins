# kepubverto for calibre — the library-view action
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""The toolbar button, the background job, and the report.

Built on what epubveri-plugins' library plugin learned in calibre 9.14:

  * **The run is a `ThreadedJob`**, so it gets a line in the Jobs panel, a
    progress bar, a log and a cancel button, and calibre stays usable.
  * **`ThreadedJob` calls its callback on the worker thread**, so the callback
    is wrapped in `Dispatcher`, constructed on the GUI thread. A callback that
    builds a dialog off the GUI thread takes calibre down.
  * **A killed job still calls the callback**, with what the worker returned,
    so a cancelled run comes back with the books it already converted.
  * **Stopping goes through `job_manager.kill_job`**, not `job.kill()`, which
    only rewrites timing fields.
  * **The binary is resolved on the GUI side before the job starts**, so a
    long run cannot have its executable replaced halfway through.
"""

from functools import partial

from qt.core import QMenu, QToolButton

from calibre.gui2 import Dispatcher, error_dialog, question_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.threaded_jobs import ThreadedJob

from calibre_plugins.kepubverto import PLUGIN_NAME, PLUGIN_VERSION
from calibre_plugins.kepubverto import config as cfg
from calibre_plugins.kepubverto import install
from calibre_plugins.kepubverto.convert import (ConversionReport,
                                                collect_jobs, convert_books)

#: The mark the report's books are shown with, searched with `=` so it is an
#: exact match and never selects another plugin's `kepubverto-something`.
MARK_TEXT = 'kepubverto'
MARK_SEARCH = 'marked:"=%s"' % MARK_TEXT

#: One run at a time: two would write formats into the same books.
JOB_TYPE = 'kepubverto_convert'

#: Above this many books, ask before starting. A whole library is always
#: asked about, whatever its size.
CONFIRM_ABOVE = 20


class KepubvertoAction(InterfaceAction):

    name = PLUGIN_NAME
    #: The caption is the plugin's name: that is what users look for. The
    #: verb is in the tooltip. The shortcut is an empty tuple, not None, so
    #: the action can be bound under Preferences / Shortcuts.
    action_spec = (PLUGIN_NAME, None, 'Convert books to KEPUB with kepubverto',
                   ())
    #: The selection is read from `library_view`, which still holds the
    #: library's selection while a device view is showing. From a device
    #: menu this would convert books the user cannot see.
    dont_add_to = frozenset([
        'toolbar-device', 'menubar-device', 'context-menu-device',
        'searchbar',
    ])
    #: Neither half of the button starts a conversion; both open the menu,
    #: and the arrow stays, like every other menu button in calibre.
    popup_type = QToolButton.ToolButtonPopupMode.MenuButtonPopup
    action_type = 'current'

    def genesis(self):
        self._dialog = None
        self.last_report = None

        self.menu = QMenu(self.gui)
        self.selection_action = self.create_menu_action(
            self.menu, 'kepubverto_selection',
            'Convert the selected books to KEPUB', shortcut=None,
            triggered=partial(self.start, 'selection'))
        self.library_action = self.create_menu_action(
            self.menu, 'kepubverto_library',
            'Convert the whole library to KEPUB', shortcut=None,
            triggered=partial(self.start, 'library'))
        self.save_action = self.create_menu_action(
            self.menu, 'kepubverto_save',
            'Save the KEPUB as .kepub.epub…', shortcut=None,
            triggered=self.save_selected)
        self.menu.addSeparator()
        self.again_action = self.create_menu_action(
            self.menu, 'kepubverto_last', 'Show the last report',
            shortcut=None, triggered=self.show_last_report)
        self.clear_action = self.create_menu_action(
            self.menu, 'kepubverto_clear', 'Clear the marks it left',
            shortcut=None, triggered=self.clear_marks)
        self.stop_action = self.create_menu_action(
            self.menu, 'kepubverto_stop', 'Stop the running conversion',
            shortcut=None, triggered=self.stop_run)
        self.menu.addSeparator()
        self.settings_action = self.create_menu_action(
            self.menu, 'kepubverto_settings', 'Settings',
            shortcut=None, triggered=self.show_settings)
        # Greyed out rather than hidden when there is nothing to do.
        self.menu.aboutToShow.connect(self._sync_menu)
        self._sync_menu()

        self.qaction.setMenu(self.menu)
        self.qaction.triggered.connect(self.show_menu)
        icon = self.load_resources(['plugin.png']).get('plugin.png')
        if icon:
            from qt.core import QIcon, QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(icon)
            self.qaction.setIcon(QIcon(pixmap))

    def _library_id(self):
        try:
            return self.gui.current_db.library_id
        except Exception:                               # noqa: BLE001
            return None

    def show_menu(self):
        """Open the menu under the button, the way the arrow does."""
        from qt.core import QCursor, QToolBar, QToolButton
        try:
            for owner in self.qaction.associatedObjects():
                if not isinstance(owner, QToolBar):
                    continue
                button = owner.widgetForAction(self.qaction)
                if isinstance(button, QToolButton) and button.isVisible():
                    return button.showMenu()
        except Exception:                               # noqa: BLE001
            pass
        self.menu.exec(QCursor.pos())

    def _sync_menu(self):
        running = self._run_going()
        self.selection_action.setEnabled(not running)
        self.library_action.setEnabled(not running)
        self.again_action.setEnabled(self.last_report is not None)
        self.clear_action.setEnabled(bool(self._marked_ids()))
        self.stop_action.setEnabled(running)

    def _our_jobs(self):
        """Our unfinished runs. `JobManager` has no per-type count in 9.14,
        so `unfinished_jobs()` is filtered by type."""
        try:
            jobs = self.gui.job_manager.unfinished_jobs()
        except Exception:                               # noqa: BLE001
            return []
        return [job for job in jobs if getattr(job, 'type', None) == JOB_TYPE]

    def _run_going(self):
        return bool(self._our_jobs())

    def stop_run(self):
        """Stop the way the Jobs panel's own button does: through the
        manager. The books already converted stay converted."""
        jobs = self._our_jobs()
        if not jobs:
            return self.gui.status_bar.show_message(
                'kepubverto: no conversion is running', 5000)
        for job in jobs:
            self.gui.job_manager.kill_job(job, self.gui)

    def show_settings(self):
        """The plugin's own settings page, one click from the toolbar."""
        from calibre.customize.ui import find_plugin
        plugin = find_plugin(PLUGIN_NAME)
        if plugin is None:                              # pragma: no cover
            return error_dialog(
                self.gui, 'kepubverto',
                'The settings page could not be opened. Preferences / '
                'Plugins / kepubverto / Customize reaches the same page.',
                show=True)
        plugin.do_user_config(self.gui)

    # -- starting ------------------------------------------------------------

    def _book_ids(self, scope):
        if scope == 'selection':
            rows = self.gui.library_view.selectionModel().selectedRows()
            if not rows:
                error_dialog(self.gui, 'kepubverto',
                             'Select some books first, or use the menu to '
                             'convert the whole library.', show=True)
                return None
            return list(map(self.gui.library_view.model().id, rows))
        return list(self.gui.current_db.new_api.all_book_ids())

    def start(self, scope='selection'):
        if self._run_going():
            return error_dialog(
                self.gui, 'kepubverto',
                'A conversion is already running. Wait for it to finish, or '
                'stop it from this menu.', show=True)

        book_ids = self._book_ids(scope)
        if book_ids is None:
            return

        db = self.gui.current_db.new_api
        replace = cfg.replace_existing()
        report = ConversionReport()
        report.scope = scope
        jobs = collect_jobs(db, book_ids, report, replace=replace)
        if not jobs:
            # Nothing to convert is still an answer worth showing: it says
            # which books were skipped, and why.
            return self._open_report(report)

        if scope == 'library' or len(jobs) > CONFIRM_ABOVE:
            replacing = ''
            if replace:
                existing = sum(1 for book_id, _t, _p in jobs
                               if db.has_format(book_id, 'KEPUB'))
                if existing:
                    replacing = (' %d of them already have a KEPUB, which '
                                 'will be replaced.' % existing)
            if not question_dialog(
                    self.gui, 'kepubverto',
                    'Convert %d books to KEPUB and add the KEPUB to each '
                    'book?%s The EPUBs are not changed. It runs in the '
                    'background; you can stop it from this menu, and what '
                    'is already converted stays.' % (len(jobs), replacing)):
                return

        try:
            binary, note = install.ensure_binary(
                autoupdate=cfg.as_bool(cfg.prefs.get('autoupdate')))
        except Exception as exc:                        # noqa: BLE001
            return error_dialog(self.gui, 'kepubverto',
                                install.install_failure(exc), show=True)
        if binary is None:
            return error_dialog(self.gui, 'kepubverto', note, show=True)
        report.note = note

        hyphens = cfg.hyphens()
        css = cfg.css_values()
        report.options = [
            ('hyphens', hyphens or 'as the book says'),
            ('css', 'yes' if css else 'none'),
            ('replace existing', 'yes' if replace else 'no'),
        ]
        job = ThreadedJob(
            JOB_TYPE,
            'kepubverto: converting %d book%s' % (len(jobs),
                                                  '' if len(jobs) == 1 else 's'),
            func=_run_conversion,
            args=(binary, jobs, db, report, hyphens, css, replace,
                  cfg.workers(jobs)),
            kwargs={}, callback=Dispatcher(self.finished), killable=True)
        self.gui.job_manager.run_threaded_job(job)
        self.gui.status_bar.show_message(
            'kepubverto is converting %d book%s…'
            % (len(jobs), '' if len(jobs) == 1 else 's'), 5000)

    def save_selected(self):
        """Save the selected books' KEPUBs as `.kepub.epub` (see `export`).

        On the GUI thread: it is a file copy per book, and the folder dialog
        has to be here anyway.
        """
        from calibre.gui2 import choose_dir, info_dialog
        from calibre_plugins.kepubverto.export import save_kepubs
        book_ids = self._book_ids('selection')
        if book_ids is None:
            return
        db = self.gui.current_db.new_api
        if not any(db.has_format(book_id, 'KEPUB') for book_id in book_ids):
            return error_dialog(
                self.gui, 'kepubverto',
                'None of the selected books has a KEPUB yet. Convert them '
                'first.', show=True)
        folder = choose_dir(self.gui, 'kepubverto-save-kepub',
                            'Save the KEPUBs to')
        if not folder:
            return
        saved, without, failed = save_kepubs(db, book_ids, folder)
        lines = []
        if without:
            lines.append('%d of the selected books have no KEPUB and were '
                         'not saved.' % len(without))
        for _book_id, title, error in failed:
            lines.append('%s: %s' % (title, error))
        if lines:
            return info_dialog(
                self.gui, 'kepubverto',
                'Saved %d KEPUB%s to %s.'
                % (len(saved), '' if len(saved) == 1 else 's', folder),
                det_msg='\n'.join(lines), show=True)
        self.gui.status_bar.show_message(
            'kepubverto: saved %d KEPUB%s as .kepub.epub to %s'
            % (len(saved), '' if len(saved) == 1 else 's', folder), 8000)

    # -- finishing -----------------------------------------------------------

    def finished(self, job):
        """On the GUI thread (through `Dispatcher`)."""
        report = job.result
        if report is None:
            # The worker raised before returning, which `convert_books` is
            # written not to do. A real bug: show it with the job log.
            return self.gui.job_exception(
                job, dialog_title='kepubverto could not finish')
        self.last_report = report
        self._refresh(report.added_ids, report.library_id)
        if report.all_clean and not report.note:
            return self.gui.status_bar.show_message(
                'kepubverto: %d book%s converted to KEPUB'
                % (len(report.books), '' if len(report.books) == 1 else 's'),
                8000)
        self._open_report(report)

    def _refresh(self, book_ids, library_id):
        """Show the new formats. Only for the library the run wrote into."""
        if not book_ids or library_id != self._library_id():
            return
        try:
            from qt.core import QModelIndex
            view = self.gui.library_view
            view.model().refresh_ids(list(book_ids))
            current = view.currentIndex()
            if current.isValid():
                view.model().current_changed(current, QModelIndex())
        except Exception:                               # noqa: BLE001
            pass
        try:
            self.gui.tags_view.recount()
        except Exception:                               # noqa: BLE001
            pass

    def _open_report(self, report):
        """Modeless, one at a time; the reference is kept."""
        from qt.core import Qt
        from calibre_plugins.kepubverto.results import ResultsDialog
        self._close_report()
        dialog = ResultsDialog(self.gui, report, self.show_books)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.finished.connect(self._report_closed)
        self._dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _report_closed(self, _result=0):
        self._dialog = None

    def _close_report(self):
        dialog, self._dialog = getattr(self, '_dialog', None), None
        if dialog is not None:
            dialog.close()

    def show_last_report(self):
        if self.last_report is None:
            return
        self._open_report(self.last_report)

    def show_books(self, book_ids, label):
        """Mark the books and filter the library view to them.

        `db.data.set_marked_ids`, not `db.set_marked_ids` (which raises in
        9.14), and it replaces the whole map, so other marks are kept.
        """
        db = self.gui.current_db
        marks = {book_id: text for book_id, text in db.data.marked_ids.items()
                 if text != MARK_TEXT}
        marks.update(dict.fromkeys(book_ids, MARK_TEXT))
        db.data.set_marked_ids(marks)
        self.gui.search.set_search_string(MARK_SEARCH)
        self.gui.status_bar.show_message(
            '%d book%s: %s' % (len(book_ids),
                               '' if len(book_ids) == 1 else 's', label), 5000)

    def _marked_ids(self):
        try:
            marked = self.gui.current_db.data.marked_ids
        except Exception:                               # noqa: BLE001
            return set()
        return {book_id for book_id, text in marked.items()
                if text == MARK_TEXT}

    def clear_marks(self):
        """Remove only our own marks."""
        db = self.gui.current_db
        ours = self._marked_ids()
        if not ours:
            return
        remaining = {book_id: text for book_id, text
                     in db.data.marked_ids.items() if book_id not in ours}
        db.data.set_marked_ids(remaining)
        if str(self.gui.search.text()).startswith('marked:'):
            self.gui.search.set_search_string('')
        self.gui.status_bar.show_message(
            'cleared %d kepubverto mark%s'
            % (len(ours), '' if len(ours) == 1 else 's'), 5000)

    def library_changed(self, db):
        """A report's book ids mean other books in another library."""
        self.last_report = None
        self._close_report()
        self._sync_menu()


def _run_conversion(binary, jobs, db, report, hyphens, css, replace, workers,
                    abort=None, log=None, notifications=None):
    """The worker. Runs in calibre's job thread and touches no Qt object.

    `db` is the `new_api` of the library the run was started in, held for
    the whole run, so a library switch in the middle cannot send formats to
    the wrong library.
    """

    def notify(fraction, title):
        if notifications is not None:
            notifications.put((fraction, title))

    def write(message):
        if log is not None:
            log(message)

    def add_format(book_id, fmt, path, replace_existing):
        # `run_hooks=False`: no file-type plugin gets to change the KEPUB on
        # its way into the library.
        return db.add_format(book_id, fmt, path, replace=replace_existing,
                             run_hooks=False)

    try:
        report.library_id = db.library_id
    except Exception:                                   # noqa: BLE001
        report.library_id = None
    write('kepubverto for calibre %s, %d books' % (PLUGIN_VERSION, len(jobs)))
    write('converter: %s' % binary)
    convert_books(binary, jobs, add_format, report=report, hyphens=hyphens,
                  css=css, replace=replace, abort=abort, notify=notify,
                  log=write, workers=workers)
    write('%d converted, %d with documents left alone, %d already KEPUB, '
          '%d not converted, %.1f s'
          % (report.count('converted'), report.count('partly'),
             report.count('already'), report.count('failed'), report.elapsed))
    return report
