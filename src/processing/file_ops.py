import os
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None
import logging
import zipfile
from pathlib import Path
from typing import Optional


def get_default_logger(name="pipeline_logger"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger


def clean_unicode(s: str) -> str:
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def classify_domain(domain, allowed_set, not_allowed_set, unlisted_set=None):
    """
    Classifies a domain:
    - Returns True if in allowed_set
    - Returns False if in not_allowed_set
    - Returns None otherwise (and adds to unlisted_set if provided)
    """
    if not isinstance(domain, str):
        domain = ""
    domain = domain.strip().lower()

    if domain in allowed_set:
        return True
    elif domain in not_allowed_set:
        return False
    else:
        if unlisted_set is not None:
            unlisted_set.add(domain)
        return None


@contextmanager
def _exclusive_lock(file_obj):
    """Advisory exclusive lock on an open file, a no-op where fcntl is absent."""
    if fcntl is None:
        yield
        return
    fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def ensure_ends_with_newline(path):
    if not path.exists():
        return
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            return
        f.seek(-1, os.SEEK_END)
        last_char = f.read(1)
        if last_char != b"\n":
            f.write(b"\n")


def append_lines_to_file(path: Path, lines: list[str]):
    """Append lines, holding an exclusive lock for the whole read-modify-write.

    The crawl-policy cache is appended to by every Celery worker, which are
    separate *processes*, so a threading lock would not help: two workers could
    interleave `ensure_ends_with_newline` and their writes and produce a line
    with two domains spliced together. flock serialises them.

    The lock is advisory and POSIX-only. On a platform without fcntl the append
    proceeds unlocked -- the previous behaviour -- rather than failing the run.
    """
    if not path.exists():
        # The crawl policy cache is gitignored, so on a fresh checkout its
        # directory does not exist either and a bare touch() would raise.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    # "a" so the file is opened for append; the lock covers the newline fix-up
    # and the writes together, which is the part that has to be atomic.
    with open(path, "a", encoding="utf-8") as f:
        with _exclusive_lock(f):
            ensure_ends_with_newline(path)
            for line in lines:
                f.write(line + "\n")
            f.flush()

    logger = get_default_logger()
    logger.info(f"[+] Appended {len(lines)} lines to {path}")


def chunked(iterable, size):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


def zip_folder(
    folder_path: str,
    zip_dest_folder: str,
    zip_file_name: str
) -> Optional[str]:
    """
    Zip the contents of `folder_path` into a zip file saved as `zip_file_name` inside `zip_dest_folder`.
    """
    logger = get_default_logger()
    try:
        os.makedirs(zip_dest_folder, exist_ok=True)
        zip_path = os.path.join(zip_dest_folder, zip_file_name)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if os.path.abspath(os.path.join(root, file)) == os.path.abspath(zip_path):
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)
        return zip_path
    except Exception as e:
        logger.error(f"Failed to create zip archive: {e}")
        return None
