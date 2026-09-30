"""
Parses an EPUB file into a structured object that can be used to serve the book via a web interface.
"""

import errno
import fcntl
import glob
import hashlib
import os
import pickle
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from urllib.parse import unquote

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment

from . import book_lock

# --- Data structures ---

@dataclass
class ChapterContent:
    """
    Represents a physical file in the EPUB (Spine Item).
    A single file might contain multiple logical chapters (TOC entries).
    """
    id: str           # Internal ID (e.g., 'item_1')
    href: str         # Filename (e.g., 'part01.html')
    title: str        # Best guess title from file
    content: str      # Cleaned HTML with rewritten image paths
    text: str         # Plain text for search/LLM context
    order: int        # Linear reading order


@dataclass
class TOCEntry:
    """Represents a logical entry in the navigation sidebar."""
    title: str
    href: str         # original href (e.g., 'part01.html#chapter1')
    file_href: str    # just the filename (e.g., 'part01.html')
    anchor: str       # just the anchor (e.g., 'chapter1'), empty if none
    children: List['TOCEntry'] = field(default_factory=list)


@dataclass
class BookMetadata:
    """Metadata"""
    title: str
    language: str
    authors: List[str] = field(default_factory=list)
    description: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    identifiers: List[str] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)


@dataclass
class Book:
    """The Master Object to be pickled."""
    metadata: BookMetadata
    spine: List[ChapterContent]  # The actual content (linear files)
    toc: List[TOCEntry]          # The navigation tree
    images: Dict[str, str]       # Map: original_path -> local_path

    # Meta info
    source_file: str
    processed_at: str
    version: str = "3.0"


# --- Utilities ---

def clean_html_content(soup: BeautifulSoup) -> BeautifulSoup:

    # Remove dangerous/useless tags
    for tag in soup(['script', 'style', 'iframe', 'video', 'nav', 'form', 'button']):
        tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove input tags
    for tag in soup.find_all('input'):
        tag.decompose()

    return soup


def extract_plain_text(soup: BeautifulSoup) -> str:
    """Extract clean text for LLM/Search usage."""
    text = soup.get_text(separator=' ')
    # Collapse whitespace
    return ' '.join(text.split())


def parse_toc_recursive(toc_list, depth=0) -> List[TOCEntry]:
    """
    Recursively parses the TOC structure from ebooklib.
    """
    result = []

    for item in toc_list:
        # ebooklib TOC items are either `Link` objects or tuples (Section, [Children])
        if isinstance(item, tuple):
            section, children = item
            entry = TOCEntry(
                title=section.title,
                href=section.href,
                file_href=section.href.split('#')[0],
                anchor=section.href.split('#')[1] if '#' in section.href else "",
                children=parse_toc_recursive(children, depth + 1)
            )
            result.append(entry)
        elif isinstance(item, epub.Link):
            entry = TOCEntry(
                title=item.title,
                href=item.href,
                file_href=item.href.split('#')[0],
                anchor=item.href.split('#')[1] if '#' in item.href else ""
            )
            result.append(entry)
        # Note: ebooklib sometimes returns direct Section objects without children
        elif isinstance(item, epub.Section):
             entry = TOCEntry(
                title=item.title,
                href=item.href,
                file_href=item.href.split('#')[0],
                anchor=item.href.split('#')[1] if '#' in item.href else ""
            )
             result.append(entry)

    return result


def get_fallback_toc(book_obj) -> List[TOCEntry]:
    """
    If TOC is missing, build a flat one from the Spine.
    """
    toc = []
    for item in book_obj.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            name = item.get_name()
            # Try to guess a title from the content or ID
            title = item.get_name().replace('.html', '').replace('.xhtml', '').replace('_', ' ').title()
            toc.append(TOCEntry(title=title, href=name, file_href=name, anchor=""))
    return toc


def extract_metadata_robust(book_obj) -> BookMetadata:
    """
    Extracts metadata handling both single and list values.
    """
    def get_list(key):
        data = book_obj.get_metadata('DC', key)
        return [x[0] for x in data] if data else []

    def get_one(key):
        data = book_obj.get_metadata('DC', key)
        return data[0][0] if data else None

    return BookMetadata(
        title=get_one('title') or "Untitled",
        language=get_one('language') or "en",
        authors=get_list('creator'),
        description=get_one('description'),
        publisher=get_one('publisher'),
        date=get_one('date'),
        identifiers=get_list('identifier'),
        subjects=get_list('subject')
    )


# --- Durable publication (staging -> validate -> atomic swap) ---
#
# A book directory holds two kinds of files:
#
#   generated  book.pkl, book.epub, images/   - rebuilt from the source EPUB
#   user-owned notes.json, ai_meta.json, ai_conversations/, chroma_db/
#
# Reprocessing regenerates the first kind and must be the identity on the
# second. Everything generated is therefore built in a *sibling* staging
# directory, validated by read-back, and only then swapped in one path at a
# time. `book.pkl` is the commit marker: every reader keys a book's existence
# on it, so it is written to the staging area first and swapped in LAST. A run
# that fails with an exception rolls back to the old book. A run that is killed
# outright (SIGKILL, power loss) inside the commit window can leave the book
# directory a mixture of old and new, but the old version's files are still in
# its staging directory, and the next run refuses to touch the book until an
# operator puts them back. No user-owned byte is lost in either case.


class ArtifactValidationError(ValueError):
    """A staged artifact failed read-back validation, so nothing was committed.

    Subclasses ``ValueError`` because it reports bad data, not a failed syscall.
    """


def _staging_dir(output_dir: str) -> str:
    """The sibling staging directory for ``output_dir``.

    A sibling (rather than a child, or a path in the system temp dir) guarantees
    the same filesystem, which is what makes the final ``os.replace`` atomic.
    """
    normalized = os.path.normpath(output_dir)
    return f"{normalized}.staging-{os.getpid()}"


#: Name of the lock file a run holds inside its own staging directory.
_LOCK_NAME = ".lock"


def _acquire_staging_lock(staging: str) -> int:
    """Take an exclusive, non-blocking flock on this run's staging directory.

    Returns the open file descriptor; the caller must keep it open for the whole
    run and close it at the end, because the lock lives on the open file
    description rather than on the file.
    """
    fd = os.open(os.path.join(staging, _LOCK_NAME), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _pid_is_running(pid: int) -> bool:
    """Whether ``pid`` is a live process. A pid we may not signal still counts."""
    if pid <= 0:
        # Signalling 0 addresses our own process group and negatives address a
        # whole group, so neither ever means "is this one process alive?".
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _staging_dir_is_owned(leftover: str) -> bool:
    """Whether some live run still owns ``leftover``.

    Liveness is decided by the lock, not by the pid embedded in the directory
    name. The kernel drops an ``flock`` when its holder dies however it dies, so
    the lock cannot go stale; a pid can be recycled onto an unrelated process,
    which would turn one SIGKILLed run into a book that can never be reprocessed
    again. The pid check survives only as a fallback for a directory created
    before its lock file existed.
    """
    lock_path = os.path.join(leftover, _LOCK_NAME)
    if os.path.isfile(lock_path):
        try:
            fd = os.open(lock_path, os.O_RDWR)
        except OSError:
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        finally:
            os.close(fd)
        return False

    suffix = os.path.basename(leftover).rsplit(".staging-", 1)[-1]
    return suffix.isdigit() and int(suffix) != os.getpid() and _pid_is_running(int(suffix))


def _is_own_staging_name(leftover: str) -> bool:
    """Whether ``leftover`` is named the way :func:`_staging_dir` names things.

    The glob that finds leftovers is wider than the set of names this module
    creates, and the excess is not hypothetical. A book folder is named
    ``{epub_stem}_data``, so an EPUB legally called ``sample_data.staging-1.epub``
    produces ``sample_data.staging-1_data`` — a real library folder that the
    pattern ``sample_data.staging-*`` matches. So does a user's own
    ``sample_data.staging-backup``. Neither has a lock file, so
    :func:`_staging_dir_is_owned` reports them unowned and the caller would
    delete them outright, ``notes.json`` and all: a data-loss path inside the
    protocol that exists to prevent data loss.

    A staging directory this module made always ends in a bare pid, and a real
    book folder never can — ``_data`` is always appended, so its suffix can never
    be all digits. Requiring digits therefore separates the two exactly.
    """
    suffix = os.path.basename(leftover).rsplit(".staging-", 1)[-1]
    return suffix.isdigit()


def _parked_asides(leftover: str) -> List[str]:
    """The superseded artifacts a dead run parked in ``leftover`` and never published over.

    Only a run killed inside the commit window, or one whose rollback failed,
    leaves this shape: its marker ``book.pkl`` is still in staging (so the new
    version never landed) and at least one ``*.superseded`` entry is beside it
    (so the old version's files were already moved out of the book directory).
    Those asides are then the only copies of the published artifacts. Top-level
    entries only — an image whose EPUB name happens to end in ``.superseded``
    must not count.

    An ``OSError`` from listing ``leftover`` propagates. A directory that cannot
    be read is not a directory known to hold nothing, and every caller has to
    decide for itself what not knowing means.
    """
    names = os.listdir(leftover)
    if 'book.pkl' not in names:
        return []
    return sorted(n for n in names if n.endswith('.superseded'))


#: The only asides the commit ever creates, each mapped to the live path it
#: was moved out of. Any other ``*.superseded`` name was not put there by this
#: module, so nothing is known about where it belongs.
_KNOWN_ASIDES: Dict[str, str] = {
    'book.epub.superseded': 'book.epub',
    'images.superseded': 'images',
}


def _describe_os_error(exc: OSError) -> str:
    """``"EACCES: Permission denied"``: the errno name an operator can search for."""
    name = errno.errorcode.get(exc.errno) if exc.errno is not None else None
    if name and exc.strerror:
        return f"{name}: {exc.strerror}"
    return str(exc)


def _unlanded_commit_message(
    output_dir: str,
    parked: List[Tuple[str, List[str]]],
    uninspectable: Optional[List[Tuple[str, str]]] = None,
) -> str:
    """Tell the operator exactly how to put the published version back by hand.

    Recovery is not automated because file names alone cannot say which side
    of the rollback the dead run was on (a half-finished rollback and a
    forward commit into a book without ``images/`` leave identical names), and
    guessing wrong destroys the old images. Each move is one ``src -> dst``
    line so the instructions can be followed — and checked — mechanically.

    So every line that can be followed mechanically has to be safe to follow.
    A move is written only for a known aside that exactly one leftover parks:
    with two candidates for one live path, the message cannot know which is the
    published version, so it lists both and leaves the choice to the operator.
    An unrecognised ``*.superseded`` entry is listed, never mapped onto a live
    path — for ``notes.json.superseded`` that path is the user's own notes, and
    for a bare ``.superseded`` it is the book directory itself. A directory
    holding either kind is marked to be kept, not deleted, because it then
    still holds a copy nobody has put back. And no line naming a directory the
    operator must not lose carries the word remove or delete.

    ``uninspectable`` pairs a leftover that could not be listed with a
    description of the error; it may hold parked files, so it is named for
    inspection only.
    """
    book_dir = os.path.abspath(output_dir)
    if parked:
        lines = [
            f"refusing to process {book_dir}: an earlier run was killed while swapping in "
            f"a new version, so {book_dir} may be a mixed old/new version. The previous "
            "version's files are parked in the staging directory below and are their "
            "only copy. Put them back by hand, in this order:",
        ]
    else:
        lines = [
            f"refusing to process {book_dir}: a staging directory left by an earlier run "
            "could not be read, so there is no telling whether it holds the previous "
            "version's files. Nothing was changed. Resolve it by hand:",
        ]

    candidates: Dict[str, List[str]] = {}
    for leftover, asides in parked:
        for aside in asides:
            if aside in _KNOWN_ASIDES:
                candidates.setdefault(aside, []).append(
                    os.path.join(os.path.abspath(leftover), aside)
                )
    for aside, paths in sorted(candidates.items()):
        if len(paths) > 1:
            live = os.path.join(book_dir, _KNOWN_ASIDES[aside])
            lines.append(
                f"  {live} was parked by more than one earlier run; inspect every "
                "candidate and choose one to put back by hand:"
            )
            lines.extend(f"    candidate: {path}" for path in paths)

    for leftover, asides in parked:
        staging = os.path.abspath(leftover)
        lines.append(f"  from {staging}:")
        settled = True
        for aside in asides:
            aside_path = os.path.join(staging, aside)
            live_name = _KNOWN_ASIDES.get(aside)
            if live_name is None:
                lines.append(
                    f"    {aside_path} is not a file this program parks; inspect it by hand"
                )
                settled = False
            elif len(candidates[aside]) > 1:
                lines.append(f"    {aside_path} is one of the candidates listed above")
                settled = False
            else:
                live = os.path.join(book_dir, live_name)
                if os.path.lexists(live):
                    lines.append(f"    remove {live}")
                lines.append(f"    {aside_path} -> {live}")
        if settled:
            lines.append(f"    then delete {staging}")
        else:
            lines.append(f"    keep {staging} until resolved")

    for leftover, error in uninspectable or []:
        lines.append(
            f"  inspect {os.path.abspath(leftover)} by hand; it may hold the only copy "
            f"of the published version ({error})"
        )
    lines.append(f"Processing {book_dir} is refused until that is done.")
    return "\n".join(lines)


def _clear_staging_dirs(output_dir: str) -> None:
    """Remove staging directories left behind by a previous crashed run.

    A staging directory that a live run still holds a lock on belongs to a
    concurrent reprocess of this same book. Deleting it would pull the floor out
    from under that run, so this refuses instead: two processes rebuilding one
    book at once is a mistake worth reporting, not racing.

    A dead run's directory is usually debris, except when the run died inside
    the commit window: then it holds the only copy of the published artifacts
    (see :func:`_parked_asides`), and this refuses as well, touching nothing.
    A leftover that cannot be listed refuses too: not being able to look is not
    evidence that there is nothing to lose. The one exception is a leftover
    that vanished between the glob and the listing, which holds nothing at all.
    Every leftover is classified before any is deleted, so one directory's
    refusal can never arrive after another's deletion.
    """
    normalized = os.path.normpath(output_dir)
    deletable: List[str] = []
    parked: List[Tuple[str, List[str]]] = []
    uninspectable: List[Tuple[str, str]] = []
    # glob.escape: a book folder is named after the EPUB file, so it can legally
    # contain '*', '?' or '[' — none of which may be read as a pattern here.
    for leftover in sorted(glob.glob(f"{glob.escape(normalized)}.staging-*")):
        if not _is_own_staging_name(leftover):
            # Someone else's directory that merely matches the pattern. Not ours
            # to reason about, and certainly not ours to delete.
            continue
        if _staging_dir_is_owned(leftover):
            raise RuntimeError(
                f"another process is already processing {normalized}; refusing to "
                f"delete the staging directory it still holds a lock on: {leftover}"
            )
        try:
            asides = _parked_asides(leftover)
        except FileNotFoundError:
            continue
        except OSError as exc:
            # Recorded, not raised: a later leftover may still be locked by a
            # live run, and that refusal has to win.
            uninspectable.append((leftover, _describe_os_error(exc)))
            continue
        if asides:
            parked.append((leftover, asides))
        else:
            deletable.append(leftover)
    if parked or uninspectable:
        raise RuntimeError(_unlanded_commit_message(normalized, parked, uninspectable))
    for leftover in deletable:
        shutil.rmtree(leftover, ignore_errors=True)


def _fsync_path(path: str) -> None:
    """fsync a file or directory so the rename that follows cannot outrun it.

    Opening a directory read-only is POSIX-only; this deliberately does not
    support Windows, which the project does not target.
    """
    flags = os.O_RDONLY
    if os.path.isdir(path):
        flags |= getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _digest(path: str) -> Tuple[str, int]:
    """Return ``(sha256_hex, size)`` for a file, read in bounded blocks."""
    hasher = hashlib.sha256()
    size = 0
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            hasher.update(block)
            size += len(block)
    return hasher.hexdigest(), size


def _write_pickle_atomically(book: Book, target_path: str) -> None:
    """Write ``book`` to ``target_path`` via a same-directory temp + os.replace.

    The temp file lives in the destination directory so the rename is atomic;
    it is flushed and fsynced before the rename, and removed if anything fails,
    so a reader never observes a truncated or partial pickle.
    """
    tmp_path = f"{target_path}.tmp"
    try:
        with open(tmp_path, 'wb') as f:
            pickle.dump(book, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    _fsync_path(os.path.dirname(target_path) or ".")


def _validate_staged_artifacts(
    staging: str,
    source_epub: str,
    image_digests: Dict[str, Tuple[str, int]],
) -> None:
    """Read every staged artifact back off disk before anything is swapped in.

    Writing a file and getting no exception is not evidence that the bytes on
    disk are the bytes intended, so each artifact is re-read and compared
    against an independently known value: the pickle must unpickle to a Book
    with a non-empty spine, the staged EPUB must hash equal to its *source*,
    and every image must hash equal to the payload it was supposed to receive
    (``image_digests`` comes from the EPUB item, never from the file that was
    just written, or a bad write would validate against itself). On any mismatch this
    raises and the caller discards the staging directory, leaving the previous
    book byte-for-byte intact.
    """
    staged_pkl = os.path.join(staging, 'book.pkl')
    try:
        with open(staged_pkl, 'rb') as f:
            reloaded = pickle.load(f)
    except Exception as exc:
        raise ArtifactValidationError(
            f"staged book.pkl could not be read back: {exc}"
        ) from exc
    if not isinstance(reloaded, Book):
        raise ArtifactValidationError(
            f"staged book.pkl unpickled to {type(reloaded).__name__}, not a Book"
        )
    if not reloaded.spine:
        raise ArtifactValidationError(
            "staged book.pkl has an empty spine: the EPUB yielded no chapters"
        )

    staged_epub = os.path.join(staging, 'book.epub')
    if not os.path.isfile(staged_epub):
        raise ArtifactValidationError("staged book.epub is missing")
    if _digest(staged_epub) != _digest(source_epub):
        raise ArtifactValidationError(
            "staged book.epub does not match the source EPUB"
        )

    for rel_path, expected in image_digests.items():
        staged_image = os.path.join(staging, rel_path)
        if not os.path.isfile(staged_image):
            raise ArtifactValidationError(f"staged image is missing: {rel_path}")
        if _digest(staged_image) != expected:
            raise ArtifactValidationError(
                f"staged image does not match what was written: {rel_path}"
            )

    for rel_path in set(reloaded.images.values()):
        if not os.path.isfile(os.path.join(staging, rel_path)):
            raise ArtifactValidationError(
                f"book.pkl references an image that was not staged: {rel_path}"
            )


def _discard(path: str) -> None:
    """Delete whatever sits at ``path``: directory, file or dangling symlink."""
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.unlink(path)


def _restore(aside: Optional[str], live: str) -> None:
    """Undo one step of the commit.

    ``aside`` is where the superseded artifact was parked, or ``None`` when
    there was no previous artifact at ``live`` — in which case undoing means
    removing what this run put there, not putting anything back. Skipping that
    case is what leaves a new ``book.epub`` beside an old ``book.pkl``.
    """
    _discard(live)
    if aside is not None:
        os.replace(aside, live)


def _commit_staged_artifacts(staging: str, output_dir: str) -> None:
    """Swap validated artifacts into ``output_dir``, marker last.

    Two invariants, and the second is the one that is easy to lose:

    1. ``book.pkl`` is written last, so a run that dies mid-commit never leaves
       a marker pointing at artifacts that were never published.
    2. The marker and the artifacts beside it always describe the *same*
       version. "The old book.pkl is still loadable" is not enough — an old
       pickle sitting next to a new EPUB and new images renders text that
       disagrees with the EPUB and 404s on every image it references. So the
       superseded ``book.epub`` and ``images/`` are renamed aside (into
       staging, hence the same filesystem) before anything new lands, and any
       failure before the marker rolls all of them back together.

       That is the whole guarantee, and it has two holes. A rollback step that
       itself fails leaves its aside in staging (``process_epub`` then keeps
       the directory), and a SIGKILL inside the window skips the rollback
       entirely. Either way the live directory can be left mixed, but the
       previous version's files are still in staging, and reprocessing refuses
       until an operator restores them (see :func:`_clear_staging_dirs`).

    Nothing here enumerates, reads or writes any path other than the three
    generated ones, which is why user-owned files come through untouched.
    """
    os.makedirs(output_dir, exist_ok=True)

    live_epub = os.path.join(output_dir, 'book.epub')
    live_images = os.path.join(output_dir, 'images')
    undo: List[Tuple[Optional[str], str]] = []
    committed = False
    try:
        # Move the superseded artifacts aside first. os.replace also refuses to
        # overwrite a non-empty directory, so images/ has to move regardless.
        # An artifact that was *absent* still gets an undo entry, with no place
        # to restore from: rolling back has to remove what this run added, not
        # only put back what it moved.
        for live, aside_name in ((live_epub, 'book.epub.superseded'),
                                 (live_images, 'images.superseded')):
            if os.path.lexists(live):
                aside = os.path.join(staging, aside_name)
                os.replace(live, aside)
                undo.append((aside, live))
            else:
                undo.append((None, live))

        os.replace(os.path.join(staging, 'book.epub'), live_epub)
        os.replace(os.path.join(staging, 'images'), live_images)
        _fsync_path(output_dir)

        # The marker. Once this lands the new book is the visible one, and the
        # transaction is over: a later failure must not roll the artifacts back
        # out from under a marker that already points at them.
        os.replace(os.path.join(staging, 'book.pkl'), os.path.join(output_dir, 'book.pkl'))
        committed = True
        _fsync_path(output_dir)
    except BaseException:
        if not committed:
            for parked, live in reversed(undo):
                try:
                    _restore(parked, live)
                except OSError as undo_error:
                    # Never let a failed rollback mask the original error - but
                    # never let it pass in silence either. This is the one
                    # outcome that leaves the book genuinely inconsistent, and
                    # the operator cannot act on what they are not told.
                    print(
                        f"WARNING: could not restore {live} after a failed commit "
                        f"({undo_error}); {output_dir} may be left inconsistent",
                        file=sys.stderr,
                    )
        raise


def _discard_own_staging(staging: str) -> None:
    """Drop this run's staging directory, unless it is the last copy of something.

    A rollback step that failed leaves its ``*.superseded`` aside parked in
    staging, and that aside is the only copy of the published version left.
    Deleting it unconditionally would turn a recoverable inconsistency into
    permanent loss. So staging is kept whenever it still holds an aside, or
    cannot be listed to find out; the next run refuses and prints how to put
    the files back. Only a staging tree known to hold nothing parked goes.
    """
    try:
        asides = _parked_asides(staging)
    except FileNotFoundError:
        return
    except OSError as exc:
        print(
            f"WARNING: kept {staging}: it could not be listed "
            f"({_describe_os_error(exc)}), so it may hold the only copy of the "
            f"published version",
            file=sys.stderr,
        )
        return
    if asides:
        print(
            f"WARNING: kept {staging}: the rollback left the previous version "
            f"parked in it ({', '.join(asides)}), and that is its only copy; "
            f"the next run will print how to put it back",
            file=sys.stderr,
        )
        return
    shutil.rmtree(staging, ignore_errors=True)


# --- Main Conversion Logic ---

def process_epub(epub_path: str, output_dir: str) -> Book:

    # 1. Load Book
    print(f"Loading {epub_path}...")
    book = epub.read_epub(epub_path)

    # 2. Extract Metadata
    metadata = extract_metadata_robust(book)

    # 3. Prepare a sibling staging directory.
    # The output directory is NOT cleared: it holds the user's annotations,
    # conversations and semantic index, none of which this function may touch.
    # normpath first: dirname("books/x/") is "books/x", which would create the
    # output directory itself as a side effect of preparing its parent.
    normalized_output = os.path.normpath(output_dir)
    books_dir = os.path.dirname(normalized_output) or "."
    os.makedirs(books_dir, exist_ok=True)
    # 018 WI-2 (ADR-0015): at most one import per book, and no reindex / notes /
    # delete while it runs. EX is taken before any staging or output dir is
    # touched and held until the staging tree is gone, so a refused import
    # changes nothing -- fresh book or existing. EX never waits: BookLockBusy.
    with book_lock.acquire(
        books_dir, os.path.basename(normalized_output), mode="exclusive", holder="import"
    ):
        _clear_staging_dirs(output_dir)
        staging = _staging_dir(output_dir)
        # exist_ok=False: if a leftover survived the cleanup above, its stale images
        # would merge into this run and be committed. Fail instead of publishing them.
        os.makedirs(staging, exist_ok=False)
        # Taken immediately, and held until the staging tree is gone: it is what a
        # later run consults to tell "still being written" from "left by a crash".
        lock_fd = _acquire_staging_lock(staging)

        # Everything after the lock sits inside the try, makedirs included: a
        # failure outside it would keep the fd, and with it the lock, for the life
        # of the process, and every later run on this book would be refused.
        try:
            images_dir = os.path.join(staging, 'images')
            os.makedirs(images_dir)
            final_book, image_digests = _build_into_staging(
                book, metadata, epub_path, staging, images_dir
            )
            _validate_staged_artifacts(staging, epub_path, image_digests)
            _commit_staged_artifacts(staging, output_dir)
        finally:
            os.close(lock_fd)
            _discard_own_staging(staging)

    print(f"Saved structured data to {os.path.join(output_dir, 'book.pkl')}")
    return final_book


def _build_into_staging(
    book, metadata: BookMetadata, epub_path: str, staging: str, images_dir: str
) -> Tuple[Book, Dict[str, Tuple[str, int]]]:
    """Write every generated artifact into ``staging``; return the Book and image digests.

    Nothing here writes to the output directory, so any failure raised from
    this function leaves the previously published book completely untouched.
    """
    # 4. Persist original EPUB for renderer compatibility.
    # A failure here is fatal: publishing a book without its EPUB would leave
    # the reader unable to render it, which is worse than not republishing.
    original_epub_path = os.path.join(staging, "book.epub")
    shutil.copy2(epub_path, original_epub_path)
    _fsync_path(original_epub_path)

    # 5. Extract Images & Build Map
    print("Extracting images...")
    image_map = {} # Key: internal_path, Value: local_relative_path
    image_digests: Dict[str, Tuple[str, int]] = {}

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            # Normalize filename
            original_fname = os.path.basename(item.get_name())
            # Sanitize filename for OS
            safe_fname = "".join([c for c in original_fname if c.isalpha() or c.isdigit() or c in '._-']).strip()

            # Save to disk
            payload = item.get_content()
            local_path = os.path.join(images_dir, safe_fname)
            with open(local_path, 'wb') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())

            # Map keys: We try both the full internal path and just the basename
            # to be robust against messy HTML src attributes
            rel_path = f"images/{safe_fname}"
            image_map[item.get_name()] = rel_path
            image_map[original_fname] = rel_path
            # Digest the payload, not the file just written: validation has to
            # compare the staged bytes against what they were *supposed* to be.
            # Hashing the file would make a bad write validate against itself.
            image_digests[rel_path] = (hashlib.sha256(payload).hexdigest(), len(payload))

    # 6. Process TOC
    print("Parsing Table of Contents...")
    toc_structure = parse_toc_recursive(book.toc)
    if not toc_structure:
        print("Warning: Empty TOC, building fallback from Spine...")
        toc_structure = get_fallback_toc(book)

    # 7. Process Content (Spine-based to preserve HTML validity)
    print("Processing chapters...")
    spine_chapters = []

    # We iterate over the spine (linear reading order)
    for i, spine_item in enumerate(book.spine):
        item_id, linear = spine_item
        item = book.get_item_with_id(item_id)

        if not item:
            continue

        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Raw content
            raw_content = item.get_content().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(raw_content, 'html.parser')

            # A. Fix Images
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if not src: continue

                # Decode URL (part01/image%201.jpg -> part01/image 1.jpg)
                src_decoded = unquote(src)
                filename = os.path.basename(src_decoded)

                # Try to find in map
                if src_decoded in image_map:
                    img['src'] = image_map[src_decoded]
                elif filename in image_map:
                    img['src'] = image_map[filename]

            # B. Clean HTML
            soup = clean_html_content(soup)

            # C. Extract Body Content only
            body = soup.find('body')
            if body:
                # Extract inner HTML of body
                final_html = "".join([str(x) for x in body.contents])
            else:
                final_html = str(soup)

            # D. Create Object
            chapter = ChapterContent(
                id=item_id,
                href=item.get_name(), # Important: This links TOC to Content
                title=f"Section {i+1}", # Fallback, real titles come from TOC
                content=final_html,
                text=extract_plain_text(soup),
                order=i
            )
            spine_chapters.append(chapter)

    # 8. Final Assembly
    final_book = Book(
        metadata=metadata,
        spine=spine_chapters,
        toc=toc_structure,
        images=image_map,
        source_file=os.path.basename(epub_path),
        processed_at=datetime.now().isoformat()
    )

    # 9. Stage the commit marker. It is written last inside staging and swapped
    # in last during the commit, so it is never the first thing readers see.
    staged_pkl = os.path.join(staging, 'book.pkl')
    with open(staged_pkl, 'wb') as f:
        pickle.dump(final_book, f)
        f.flush()
        os.fsync(f.fileno())
    _fsync_path(staging)

    return final_book, image_digests


def save_to_pickle(book: Book, output_dir: str):
    """Publish ``book`` as ``output_dir/book.pkl`` without ever truncating the old one.

    ``process_epub`` publishes its own marker as part of its atomic commit, so
    nothing in this module calls this any more. It stays as the supported way
    for other code to republish a Book it has modified in memory.
    """
    p_path = os.path.join(output_dir, 'book.pkl')
    _write_pickle_atomically(book, p_path)
    print(f"Saved structured data to {p_path}")


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Process EPUBs for Reader3 Pro")
    parser.add_argument("epub", nargs="?", help="Path to .epub file to process")
    parser.add_argument("--index", dest="index_book_id", help="Index a processed book folder (e.g. dracula_data)")
    parser.add_argument("--force", action="store_true", help="Force re-index (semantic search)")
    args = parser.parse_args(argv)

    books_dir = os.environ.get("READER3_BOOKS_DIR", "books")

    if args.index_book_id:
        from .vector_search import BookVectorIndex

        book_id = args.index_book_id
        book_dir = os.path.join(books_dir, book_id)
        if not os.path.exists(os.path.join(book_dir, "book.pkl")):
            raise SystemExit(f"Book not found or not processed: {book_id} (expected {book_dir}/book.pkl)")
        idx = BookVectorIndex(book_id, books_dir=books_dir)
        try:
            meta = idx.index_book(force_reindex=args.force)
        except (book_lock.BookLockError, book_lock.BookGone) as e:
            # 018 WI-2: another writer holds the book (the message names its
            # category), or it changed / vanished under us. Same exit shape as
            # every other failure here: non-zero, one readable line, no traceback.
            raise SystemExit(str(e))
        except RuntimeError as e:
            # 缺 [semantic] extra 时 _require_semantic_deps 抛的就是 RuntimeError，
            # 它带着一句用户照着做就能修好的话。让它一路穿到顶层，终端上得到的是一屏
            # traceback——而这个函数里其它每一个失败出口（书没找到、没给参数、文件
            # 不存在）都是 SystemExit(msg)。这里跟着它们走。
            raise SystemExit(str(e))
        print(f"Indexed {book_id}: {meta.get('chunk_count', 0)} chunks using {meta.get('model_name')}")
        return 0

    if not args.epub:
        raise SystemExit("Usage: reader3 <file.epub> OR reader3 --index <book_id>")

    epub_file = args.epub
    if not os.path.exists(epub_file):
        raise SystemExit("File not found.")

    base = os.path.splitext(os.path.basename(epub_file))[0]
    out_dir = str(Path(books_dir) / (base + "_data"))

    # process_epub publishes book.pkl itself, as the last step of its atomic
    # commit. Calling save_to_pickle here too would flip the marker twice.
    book_obj = process_epub(epub_file, out_dir)
    print("\n--- Summary ---")
    print(f"Title: {book_obj.metadata.title}")
    print(f"Authors: {', '.join(book_obj.metadata.authors)}")
    print(f"Physical Files (Spine): {len(book_obj.spine)}")
    print(f"TOC Root Items: {len(book_obj.toc)}")
    print(f"Images extracted: {len(book_obj.images)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
