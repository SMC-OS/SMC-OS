"""Read-only check that the uploads directory and the `documents` table agree.

Reports, never changes anything:
  * orphan files   - on disk, no `documents` row (older than --min-age-minutes, so an upload that is
                     being written right now is not reported)
  * missing files  - a `documents` row whose file is not on disk (data loss or an interrupted restore)
  * size mismatches - the row's size_bytes differs from the file
Only counts and file *names* (random UUIDs) are printed, never file contents or customer data.
Exit 0 = consistent, 1 = findings. Run against the real volume during the recovery drill.

  UPLOAD_DIR=/var/lib/simo-os/uploads python -m scripts.qa.uploads_integrity_check   (inside the container)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROBE_PREFIX = ".simo-os-write-probe-"


def compare(rows: dict[str, int], files: dict[str, tuple[int, float]], *, now: float, min_age_s: float) -> dict:
    """rows: storage_filename -> size_bytes; files: name -> (size, mtime)."""
    orphans = sorted(n for n, (_s, mtime) in files.items() if n not in rows and not n.startswith(PROBE_PREFIX) and now - mtime >= min_age_s)
    missing = sorted(n for n in rows if n not in files)
    mismatched = sorted(n for n, size in rows.items() if n in files and files[n][0] != size)
    return {"orphan_files": orphans, "missing_files": missing, "size_mismatches": mismatched}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-age-minutes", type=float, default=10.0)
    args = parser.parse_args(argv)
    from app.core.config import settings
    from app.database.database import SessionLocal
    from app.database.models import Document

    directory = Path(settings.upload_dir)
    files = {p.name: (p.stat().st_size, p.stat().st_mtime) for p in directory.iterdir() if p.is_file()} if directory.is_dir() else {}
    with SessionLocal() as db:
        rows = {r.storage_filename: r.size_bytes for r in db.query(Document).all()}
    result = compare(rows, files, now=time.time(), min_age_s=args.min_age_minutes * 60)
    summary = {k: len(v) for k, v in result.items()} | {"documents": len(rows), "files": len(files)}
    print(json.dumps({"summary": summary, **{k: v[:50] for k, v in result.items()}}, indent=1))
    return 1 if any(result.values()) else 0


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    sys.exit(main())
