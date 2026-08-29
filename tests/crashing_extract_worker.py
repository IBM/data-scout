# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""A stand-in for src.pipeline.extract_worker that segfaults on a marker document.

A real crash depends on a specific malformed document that killed the parser in
production and was never captured, so this reproduces the *shape* of that
failure -- a genuine SIGSEGV, mid-chunk, after some results were already written
-- to prove the parent recovers.
"""
import json
import os
import pickle
import signal
import sys

CRASH_MARKER = b"__CRASH_THIS_DOCUMENT__"


def main(argv):
    in_path, out_path, progress_path = argv[1], argv[2], argv[3]
    with open(in_path, "rb") as fh:
        items = pickle.load(fh)

    with open(out_path, "w", encoding="utf-8") as out, \
         open(progress_path, "w", encoding="utf-8") as progress:
        for index, content in items:
            progress.write(f"{index}\n")
            progress.flush()

            if content == CRASH_MARKER:
                out.flush()
                os.kill(os.getpid(), signal.SIGSEGV)  # the real failure mode

            out.write(json.dumps({"i": index, "text": "ok", "status": "Success"}) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
