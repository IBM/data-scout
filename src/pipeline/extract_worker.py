# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""Document extraction, run as a child process so a native crash is survivable.

Extraction calls trafilatura, which parses with libxml2 -- a C extension. A
malformed or deeply nested document can segfault it, and a SIGSEGV kills the
whole OS process. Extraction used to run in a thread pool inside the Celery
worker, and threads share one address space, so a single bad document took the
worker down mid-run and discarded every document already downloaded.

Run as a separate process, that same crash is only an exit code the parent can
read. Two details make the crash recoverable rather than merely survivable:

* results are written to `out_path` one line at a time and flushed, so whatever
  finished before the crash is still on disk; and
* the index about to be parsed is written to `progress_path` and flushed first,
  so the last line of that file names the document that killed us.

Invoked as `python -m src.pipeline.extract_worker <in> <out> <progress>` rather
than through multiprocessing, because a Celery prefork task runs in a *daemonic*
process and Python forbids those from starting multiprocessing children --
plain subprocess is not subject to that restriction.
"""
import json
import pickle
import sys

from src.processing.text_extraction import extract_simple_document


def extract_one(content):
    """Return (text, status) for one document, mirroring the in-process contract."""
    if content is None:
        return "", "Success: No content to extract"
    try:
        text = extract_simple_document(content)
        return text or "", "Success"
    except Exception as e:
        return "", f"Error: {str(e)}"


def main(argv):
    if len(argv) != 4:
        print(f"usage: {argv[0]} <in_path> <out_path> <progress_path>", file=sys.stderr)
        return 2

    in_path, out_path, progress_path = argv[1], argv[2], argv[3]
    with open(in_path, "rb") as fh:
        items = pickle.load(fh)

    with open(out_path, "w", encoding="utf-8") as out, \
         open(progress_path, "w", encoding="utf-8") as progress:
        for index, content in items:
            # Flushed before parsing: if libxml2 takes the process down, this is
            # the last line in the file and so names the offending document.
            progress.write(f"{index}\n")
            progress.flush()

            text, status = extract_one(content)

            out.write(json.dumps({"i": index, "text": text, "status": status}) + "\n")
            out.flush()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
