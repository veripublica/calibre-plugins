# kepubverto for calibre — the conversion run
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Convert many books and record what happened to each.

**The stored EPUB is converted as it is.** It is read straight from the
library (`format_abspath`) and handed to kepubverto, never through calibre's
conversion pipeline, which parses a book into its own model and writes it out
again before an output plugin sees it. That rewriting is what kepubverto
exists to avoid, so this plugin is a library action and not a conversion
output plugin (agreed with kepubverto, 2026-10-24).

Each book is converted into a fresh temporary folder and the result is added
to the book as calibre's `KEPUB` format. Adding happens on the job's own
thread, one book at a time; calibre's `db.new_api` is thread-safe, and the
pool only ever runs kepubverto.

What a book's outcome can be:

  * `converted`: every content document converted; the KEPUB was added.
  * `partly`: kepubverto's exit 1. The book was written, but some documents
    were left as they were (each one a finding). The KEPUB was added anyway
    (agreed with kepubverto): a document left alone is copied byte for byte,
    so the KEPUB is never worse than the EPUB, only without spans there.
  * `already`: the EPUB is already a KEPUB. Nothing was added.
  * `has kepub`: the book already had a KEPUB and replacing is off.
  * `no epub`: no EPUB to convert, or its file is missing.
  * `failed`: kepubverto could not convert it, or refused (its reason is the
    error), or the KEPUB could not be added.
"""

import os
import shutil
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime

from calibre_plugins.kepubverto import PLUGIN_VERSION
from calibre_plugins.kepubverto.client import runner
from calibre_plugins.kepubverto.client.envelope import EnvelopeError

SOURCE_FORMAT = 'EPUB'
TARGET_FORMAT = 'KEPUB'

CONVERTED = 'converted'
PARTLY = 'partly'
ALREADY = 'already'
HAS_KEPUB = 'has kepub'
NO_EPUB = 'no epub'
FAILED = 'failed'

#: Report order: what needs a look first.
OUTCOME_ORDER = (FAILED, PARTLY, NO_EPUB, HAS_KEPUB, ALREADY, CONVERTED)

#: How each outcome reads in the report.
OUTCOME_LABELS = {
    CONVERTED: 'Converted',
    PARTLY: 'Converted, some documents left as they were',
    ALREADY: 'Already a KEPUB',
    HAS_KEPUB: 'Skipped: has a KEPUB',
    NO_EPUB: 'Skipped: no EPUB',
    FAILED: 'Not converted',
}

#: Outcomes that put a new KEPUB into the library.
ADDED = (CONVERTED, PARTLY)


class BookResult:
    """What happened to one book."""

    __slots__ = ('book_id', 'title', 'path', 'outcome', 'error', 'findings',
                 'summary')

    def __init__(self, book_id, title, path=None, outcome=None):
        self.book_id = book_id
        self.title = title
        self.path = path
        self.outcome = outcome
        self.error = None
        #: The documents left as they were: `Finding`s.
        self.findings = []
        self.summary = {}

    @property
    def detail(self):
        """One line for the report's detail column."""
        if self.error:
            return self.error
        if self.outcome == PARTLY:
            shown = ', '.join(f.location or '?' for f in self.findings[:3])
            more = len(self.findings) - 3
            return '%d left as they were: %s%s' % (
                len(self.findings), shown,
                ' and %d more' % more if more > 0 else '')
        if self.outcome in ADDED and self.summary:
            return '%d documents, %d spans' % (
                self.summary.get('documents', 0), self.summary.get('spans', 0))
        return ''


def describe_machine():
    """`(label, value)` pairs for the system the run was made on. Never
    raises: no fact here is worth failing a run for."""
    import platform
    import sys
    pairs = []

    def add(label, value):
        if value:
            pairs.append((label, str(value)))

    try:
        if sys.platform == 'darwin':
            add('system', 'macOS %s' % platform.mac_ver()[0])
        elif os.name == 'nt':
            release, build = platform.win32_ver()[:2]
            add('system', ('Windows %s (%s)' % (release, build)).strip())
        else:
            add('system', ('%s %s' % (platform.system(),
                                      platform.release())).strip())
        add('processor', platform.machine())
    except Exception:                                   # noqa: BLE001
        pass
    add('cores', os.cpu_count())
    try:
        from calibre.constants import __version__ as calibre_version
        add('calibre', calibre_version)
    except Exception:                                   # noqa: BLE001
        pass
    return pairs


class ConversionReport:
    """Everything one run produced. Built by `collect_jobs` and
    `convert_books`, read by the dialog."""

    def __init__(self):
        #: Every book asked for, in the order asked, including the skipped.
        self.books = []
        self.requested = 0
        self.elapsed = 0.0
        self.tool_version = ''
        self.cancelled = False
        self.note = None
        self.started_at = None
        self.workers = 1
        self.machine = []
        #: 'library' or 'selection'.
        self.scope = 'selection'
        #: The options the run used, as shown in the report.
        self.options = []
        #: calibre's id for the library the run wrote into. Set by the
        #: worker; the view is refreshed only if it is still the open one.
        self.library_id = None

    def count(self, outcome):
        return sum(1 for b in self.books if b.outcome == outcome)

    def ids(self, outcomes):
        wanted = set(outcomes)
        return {b.book_id for b in self.books if b.outcome in wanted}

    @property
    def added_ids(self):
        return self.ids(ADDED)

    @property
    def all_clean(self):
        """Every book asked for was converted cleanly: nothing to look at."""
        return bool(self.books) and all(b.outcome == CONVERTED
                                        for b in self.books)

    def summary_line(self):
        parts = []
        for outcome in OUTCOME_ORDER[::-1]:
            n = self.count(outcome)
            if n:
                parts.append('%s: %d' % (OUTCOME_LABELS[outcome], n))
        if self.cancelled:
            parts.append('cancelled, %d not started' % self.not_started)
        return '; '.join(parts) or 'nothing to convert'

    @property
    def not_started(self):
        """Books a cancel stopped before they were handed out."""
        return max(0, self.requested - len(self.books))

    def conditions(self):
        """What the run was made with, for the window and the clipboard."""
        pairs = []
        if self.started_at is not None:
            pairs.append(('converted', self.started_at.strftime('%Y-%m-%d %H:%M')))
        pairs.append(('books', str(self.requested)))
        if self.elapsed:
            pairs.append(('took', '%.0f s' % self.elapsed))
        pairs.append(('at once', str(self.workers)))
        if self.tool_version:
            pairs.append(('kepubverto', self.tool_version))
        pairs.append(('plugin', PLUGIN_VERSION))
        pairs.extend(self.options)
        pairs.extend(self.machine)
        return pairs

    def sorted_books(self):
        rank = {o: i for i, o in enumerate(OUTCOME_ORDER)}
        return sorted(self.books, key=lambda b: (rank.get(b.outcome, 9),
                                                 (b.title or '').lower()))


def worker_cap():
    """Physical cores less two, at least one. Two are kept for the system and
    calibre's own UI thread."""
    cores = None
    try:
        import psutil
        cores = psutil.cpu_count(logical=False)
    except Exception:                                   # noqa: BLE001
        cores = None
    if not cores:
        cores = os.cpu_count() or 1
    return max(1, cores - 2)


def recommended_workers(jobs=(), cap=None):
    """The cap, or the number of books if that is fewer."""
    cap = worker_cap() if cap is None else cap
    count = len(list(jobs))
    if count:
        cap = min(cap, count)
    return max(1, cap)


def collect_jobs(db, book_ids, report, replace=False):
    """`(book_id, title, epub_path)` for every book there is something to do
    for. Every other book is recorded in `report` with its reason, never
    skipped silently.

    `db` is calibre's `new_api` (`Cache`).
    """
    jobs = []
    report.requested = len(book_ids)
    for book_id in book_ids:
        try:
            title = db.field_for('title', book_id)
        except Exception:                               # noqa: BLE001
            title = None
        title = title or '(unknown)'
        try:
            path = db.format_abspath(book_id, SOURCE_FORMAT)
        except Exception:                               # noqa: BLE001
            path = None
        if not path or not os.path.exists(path):
            report.books.append(BookResult(book_id, title, path, NO_EPUB))
            continue
        if not replace:
            try:
                has_kepub = db.has_format(book_id, TARGET_FORMAT)
            except Exception:                           # noqa: BLE001
                has_kepub = False
            if has_kepub:
                report.books.append(BookResult(book_id, title, path,
                                               HAS_KEPUB))
                continue
        jobs.append((book_id, title, path))
    return jobs


#: How many individual failures the log names before it stops naming them.
MAX_LOGGED_FAILURES = 50


def convert_books(binary, jobs, add_format, report=None, hyphens=None, css=(),
                  replace=False, abort=None, notify=None, log=None, workers=1,
                  timeout=runner.DEFAULT_TIMEOUT):
    """Convert `jobs` and add each result through `add_format`.

    `add_format(book_id, fmt, path, replace)` is `db.new_api.add_format` in
    calibre (with `run_hooks=False` bound in) and a stub in the tests. It
    returns whether a format was added.

    **One process per book, several at once.** A cancel takes effect between
    books (`abort` is checked before each one is handed out), and what was
    already converted stays in the library and in the report.

    **Only this thread touches `report` and the library.** The pool runs
    kepubverto and hands back an envelope; everything else happens here.
    """
    report = report if report is not None else ConversionReport()
    started = time.time()
    workers = max(1, int(workers or 1))
    report.started_at = datetime.now()
    report.workers = workers
    report.machine = describe_machine()
    step = max(1, len(jobs) // 40)
    failures_logged = [0]
    tmp_root = tempfile.mkdtemp(prefix='kepubverto-')

    def trace(message):
        if log is not None:
            log(message)

    def fail(result, error):
        result.outcome = FAILED
        result.error = error
        if failures_logged[0] < MAX_LOGGED_FAILURES:
            trace('not converted: %s - %s' % (result.title, error))
        elif failures_logged[0] == MAX_LOGGED_FAILURES:
            trace('further failures are in the report, not the log')
        failures_logged[0] += 1

    def convert(index):
        """The only thing that runs off this thread."""
        book_id, _title, path = jobs[index]
        folder = os.path.join(tmp_root, str(index))
        os.makedirs(folder)
        output = os.path.join(folder, 'book.kepub.epub')
        try:
            envelope = runner.run_kepubverto(binary, path, output,
                                             hyphens=hyphens, css=css,
                                             timeout=timeout)
            return envelope, output, None
        except EnvelopeError as exc:
            return None, output, str(exc)
        except Exception as exc:                        # noqa: BLE001
            # A timeout, a killed process, a file that vanished. None of it
            # is a reason to lose the other books.
            return None, output, '%s: %s' % (type(exc).__name__, exc)

    def collect(index, outcome):
        """Fold one finished book into the report and the library."""
        book_id, title, path = jobs[index]
        result = BookResult(book_id, title, path)
        slots[index] = result
        envelope, output, error = outcome
        try:
            if error is not None:
                return fail(result, error)
            if not report.tool_version:
                report.tool_version = envelope.tool_version
            result.summary = dict(envelope.summary)
            result.findings = list(envelope.findings)
            if envelope.could_not_convert:
                return fail(result, envelope.error
                            or 'kepubverto could not convert this book')
            if envelope.already_kepub:
                result.outcome = ALREADY
                return
            written = envelope.output or output
            if not os.path.isfile(written):
                return fail(result, 'kepubverto reported success but wrote '
                                    'no file')
            try:
                added = add_format(book_id, TARGET_FORMAT, written, replace)
            except Exception as exc:                    # noqa: BLE001
                return fail(result, 'the KEPUB could not be added to the '
                                    'library: %s' % exc)
            if added is False:
                # Only when replacing is off and a KEPUB appeared meanwhile.
                result.outcome = HAS_KEPUB
                return
            result.outcome = PARTLY if envelope.findings else CONVERTED
        finally:
            shutil.rmtree(os.path.join(tmp_root, str(index)),
                          ignore_errors=True)

    if workers > 1:
        trace('%d workers' % workers)

    # Filled by index, so the report keeps the order the books were asked in.
    slots = [None] * len(jobs)
    completed = 0
    handed_out = 0
    cancelled = False
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = {}
            while True:
                while len(pending) < workers and handed_out < len(jobs):
                    if abort is not None and abort.is_set():
                        cancelled = True
                        break
                    index = handed_out
                    handed_out += 1
                    if notify is not None:
                        notify(float(completed) / max(1, len(jobs)),
                               jobs[index][1])
                    if completed and completed % step == 0:
                        spent = time.time() - started
                        trace('%d/%d, %.0f s, %.3f s/book'
                              % (completed, len(jobs), spent,
                                 spent / completed))
                    pending[pool.submit(convert, index)] = index
                if not pending:
                    break
                done, _ = wait(list(pending), return_when=FIRST_COMPLETED)
                for future in done:
                    collect(pending.pop(future), future.result())
                    completed += 1
                if cancelled and not pending:
                    break
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    if cancelled:
        report.cancelled = True
        trace('cancelled after %d of %d' % (completed, len(jobs)))
    report.books.extend(r for r in slots if r is not None)
    report.elapsed = time.time() - started
    return report
