"""Create a deterministic, portable upload archive and paired integrity manifest.

This utility is intentionally offline: it neither contacts Railway nor uploads
artifacts.  Operators provide the already-selected database recovery point.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import tempfile
from typing import BinaryIO

import recovery_safety as safety
from recovery_safety import validate_portable_relative_path, validate_recovery_metadata


ACTIVE_UPLOAD_MOUNT = "/var/lib/simo-os/uploads"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHUNK_SIZE = 1024 * 1024


class RecoveryError(ValueError):
    """A non-sensitive validation error suitable for the command boundary."""


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        _resolved(candidate).relative_to(_resolved(parent))
    except ValueError:
        return False
    return True


def _is_active_mount_path(path: Path) -> bool:
    # Keep the Linux production mount check meaningful when the offline tool is
    # tested on another host OS as well.
    normalized = str(path).replace("\\", "/")
    active = ACTIVE_UPLOAD_MOUNT.rstrip("/")
    if normalized == active or normalized.startswith(active + "/"):
        return True
    return _is_within(path, Path(ACTIVE_UPLOAD_MOUNT))


def _validate_output_path(path: Path, label: str) -> Path:
    resolved = _resolved(path)
    if _is_within(resolved, REPOSITORY_ROOT) or _is_active_mount_path(path):
        raise RecoveryError(f"{label} location is not permitted")
    if not resolved.parent.is_dir():
        raise RecoveryError(f"{label} parent directory is unavailable")
    return resolved


def _is_reparse(stat_result: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(stat_result, "st_file_attributes", 0) & reparse_flag)


def _safe_lstat(path: Path, message: str) -> os.stat_result:
    try:
        result = path.lstat()
    except OSError as exc:
        raise RecoveryError(message) from exc
    if _is_reparse(result):
        raise RecoveryError(message)
    return result


def _same_path(path: Path, opened: os.stat_result, message: str) -> None:
    current = _safe_lstat(path, message)
    if not os.path.samestat(opened, current):
        raise RecoveryError(message)


class _PinnedSource:
    def __init__(
        self,
        relative: str,
        path: Path,
        handle: BinaryIO,
        opened: os.stat_result,
    ) -> None:
        self.relative = relative
        self.path = path
        self.handle = handle
        self.opened = opened


def _close_sources(files: list[object]) -> None:
    for item in files:
        if isinstance(item, _PinnedSource):
            item.handle.close()


def _validate_metadata(recovery_point: str, created_at: str) -> None:
    try:
        validate_recovery_metadata(recovery_point, created_at)
    except ValueError as exc:
        raise RecoveryError("recovery metadata is unsafe")


def _source_files(source: Path) -> tuple[os.stat_result, list[_PinnedSource]]:
    root_opened = _safe_lstat(source, "source directory is invalid")
    if not stat.S_ISDIR(root_opened.st_mode) or source.is_symlink():
        raise RecoveryError("source directory is invalid")
    root = source.resolve(strict=True)
    _same_path(root, root_opened, "source directory changed during discovery")
    files: list[_PinnedSource] = []
    try:
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            current_opened = _safe_lstat(current_path, "source contains a reparse point")
            if not stat.S_ISDIR(current_opened.st_mode):
                raise RecoveryError("source contains a non-directory component")
            for directory in directories:
                child = current_path / directory
                child_stat = _safe_lstat(child, "source contains a symlink or reparse point")
                if not stat.S_ISDIR(child_stat.st_mode) or child.is_symlink():
                    raise RecoveryError("source contains a symlink or reparse point")
            for filename in filenames:
                candidate = current_path / filename
                before = _safe_lstat(candidate, "source contains a non-regular file")
                if candidate.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise RecoveryError("source contains a non-regular or multi-link file")
                flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                try:
                    fd = os.open(candidate, flags)
                    handle = os.fdopen(fd, "rb")
                except OSError as exc:
                    raise RecoveryError("source file could not be pinned") from exc
                opened = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or not os.path.samestat(before, opened)
                ):
                    handle.close()
                    raise RecoveryError("source file identity is invalid")
                try:
                    candidate.resolve(strict=True).relative_to(root)
                except ValueError as exc:
                    handle.close()
                    raise RecoveryError("source path escapes its root") from exc
                relative = candidate.relative_to(root).as_posix()
                if not relative or PurePosixPath(relative).is_absolute():
                    handle.close()
                    raise RecoveryError("source contains an invalid path")
                files.append(_PinnedSource(relative, candidate, handle, opened))
                try:
                    safety.validate_entry_count(len(files))
                except ValueError as exc:
                    raise RecoveryError("source exceeds recovery limits") from exc
            _same_path(current_path, current_opened, "source directory changed during discovery")
            _same_path(root, root_opened, "source directory changed during discovery")
        return root_opened, sorted(files, key=lambda item: item.relative)
    except BaseException:
        _close_sources(files)
        raise


class _HashingReader:
    def __init__(self, source: BinaryIO) -> None:
        self.source = source
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self.source.read(size)
        self.digest.update(chunk)
        self.size += len(chunk)
        return chunk


def _write_archive(
    archive_path: Path,
    source_files: list[object],
    archive_handle: BinaryIO | None = None,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    owned_handle = archive_handle is None
    handle = archive_handle if archive_handle is not None else archive_path.open("w+b")
    try:
        handle.seek(0)
        handle.truncate(0)
        with tarfile.open(fileobj=handle, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for item in source_files:
                if isinstance(item, _PinnedSource):
                    relative, source, raw, before = item.relative, item.path, item.handle, item.opened
                else:
                    relative, source = item
                    raw, before = source.open("rb"), source.stat()
                raw.seek(0)
                current_handle = os.fstat(raw.fileno())
                if not os.path.samestat(before, current_handle):
                    if not isinstance(item, _PinnedSource):
                        raw.close()
                    raise RecoveryError("source changed while archive was created")
                info = tarfile.TarInfo(relative)
                info.size = before.st_size
                info.mode = 0o600
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                reader = _HashingReader(raw)
                archive.addfile(info, reader)
                after_handle = os.fstat(raw.fileno())
                after_path = _safe_lstat(source, "source changed while archive was created")
                if not isinstance(item, _PinnedSource):
                    raw.close()
                if (
                    reader.size != before.st_size
                    or not os.path.samestat(before, after_handle)
                    or not os.path.samestat(before, after_path)
                    or (after_handle.st_size, after_handle.st_mtime_ns)
                    != (before.st_size, before.st_mtime_ns)
                ):
                    raise RecoveryError("source changed while archive was created")
                entries.append({"relative_path": relative, "sha256": reader.digest.hexdigest(), "size_bytes": reader.size})
        handle.flush()
        os.fsync(handle.fileno())
        handle.seek(0)
        return entries
    finally:
        if owned_handle:
            handle.close()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_handle(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    handle.seek(0)
    for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


def _verify_temp(path: Path, handle: BinaryIO) -> os.stat_result:
    opened = os.fstat(handle.fileno())
    current = _safe_lstat(path, "temporary recovery output changed")
    if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(opened, current):
        raise RecoveryError("temporary recovery output changed")
    return opened


def _publish_noclobber(
    temporary: Path,
    target: Path,
    opened: os.stat_result,
    parent_opened: os.stat_result,
) -> os.stat_result:
    _same_path(target.parent, parent_opened, "recovery output parent changed")
    current = _safe_lstat(temporary, "temporary recovery output changed")
    if not os.path.samestat(opened, current):
        raise RecoveryError("temporary recovery output changed")
    linked = False
    try:
        os.link(temporary, target)
        linked = True
        published = _safe_lstat(target, "recovery output publication failed")
        if not os.path.samestat(opened, published):
            raise RecoveryError("recovery output publication failed")
        temporary.unlink()
        _same_path(target.parent, parent_opened, "recovery output parent changed")
        return published
    except OSError as exc:
        if linked:
            _rollback_exact(target, opened)
        raise RecoveryError("recovery output publication failed") from exc
    except BaseException:
        if linked:
            _rollback_exact(target, opened)
        raise


def _rollback_exact(path: Path, published: os.stat_result | None) -> None:
    if published is None:
        return
    try:
        current = path.lstat()
        if os.path.samestat(current, published):
            path.unlink()
    except FileNotFoundError:
        pass


def create_bundle(source_dir: Path, archive_path: Path, manifest_path: Path, database_recovery_point: str, created_at: str) -> dict[str, object]:
    _validate_metadata(database_recovery_point, created_at)
    archive_path = _validate_output_path(archive_path, "archive")
    manifest_path = _validate_output_path(manifest_path, "manifest")
    if archive_path == manifest_path or archive_path.exists() or manifest_path.exists():
        raise RecoveryError("recovery output already exists or conflicts")
    # Preserve the final path component for lstat/reparse validation; resolving
    # it first would silently turn a source-root symlink into its target.
    source_root = source_dir.expanduser().absolute()
    discovered = _source_files(source_root)
    if isinstance(discovered, tuple) and isinstance(discovered[0], os.stat_result):
        source_root_opened, source_files = discovered
    else:
        source_root_opened = _safe_lstat(source_root, "source directory is invalid")
        source_files = discovered
    try:
        collision_keys: set[str] = set()
        total_size = 0
        try:
            safety.validate_entry_count(len(source_files))
        except ValueError as exc:
            raise RecoveryError("source exceeds recovery limits") from exc
        for item in source_files:
            relative = item.relative if isinstance(item, _PinnedSource) else item[0]
            try:
                _exact, collision_key = validate_portable_relative_path(relative)
                member_size = item.opened.st_size if isinstance(item, _PinnedSource) else item[1].stat().st_size
                total_size = safety.add_member_size(total_size, member_size)
            except ValueError as exc:
                raise RecoveryError("source exceeds recovery portability limits") from exc
            if collision_key in collision_keys:
                raise RecoveryError("source contains colliding paths")
            collision_keys.add(collision_key)
    except BaseException:
        _close_sources(source_files)
        raise
    archive_temp: Path | None = None
    manifest_temp: Path | None = None
    archive_handle: BinaryIO | None = None
    manifest_handle: BinaryIO | None = None
    published_archive: os.stat_result | None = None
    try:
        archive_parent_opened = _safe_lstat(archive_path.parent, "archive parent directory is unavailable")
        manifest_parent_opened = _safe_lstat(manifest_path.parent, "manifest parent directory is unavailable")
        archive_fd, archive_name = tempfile.mkstemp(prefix=".matched-upload-", suffix=".tar", dir=archive_path.parent)
        archive_handle = os.fdopen(archive_fd, "w+b")
        archive_temp = Path(archive_name)
        entries = _write_archive(archive_temp, source_files, archive_handle)
        _same_path(source_root, source_root_opened, "source directory changed while archive was created")
        archive_temp_opened = _verify_temp(archive_temp, archive_handle)
        payload: dict[str, object] = {
            "archive_sha256": _sha256_handle(archive_handle),
            "created_at": created_at,
            "database_recovery_point": database_recovery_point,
            "entries": entries,
        }
        manifest_bytes = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        ).encode("utf-8")
        try:
            safety.validate_manifest_size(len(manifest_bytes))
        except ValueError as exc:
            raise RecoveryError("manifest exceeds recovery limits") from exc
        manifest_fd, manifest_name = tempfile.mkstemp(prefix=".matched-upload-", suffix=".json", dir=manifest_path.parent)
        manifest_handle = os.fdopen(manifest_fd, "w+b")
        manifest_handle.write(manifest_bytes)
        manifest_handle.flush()
        os.fsync(manifest_handle.fileno())
        manifest_handle.seek(0)
        manifest_temp = Path(manifest_name)
        manifest_temp_opened = _verify_temp(manifest_temp, manifest_handle)
        archive_handle.close()
        archive_handle = None
        published_archive = _publish_noclobber(
            archive_temp, archive_path, archive_temp_opened, archive_parent_opened
        )
        archive_temp = None
        manifest_handle.close()
        manifest_handle = None
        try:
            _publish_noclobber(
                manifest_temp, manifest_path, manifest_temp_opened, manifest_parent_opened
            )
        except BaseException:
            _rollback_exact(archive_path, published_archive)
            raise
        manifest_temp = None
        return payload
    finally:
        _close_sources(source_files)
        for handle in (archive_handle, manifest_handle):
            if handle is not None:
                handle.close()
        for temporary in (archive_temp, manifest_temp):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an offline matched upload recovery bundle.")
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--archive-path", required=True, type=Path)
    parser.add_argument("--manifest-path", required=True, type=Path)
    parser.add_argument("--database-recovery-point", required=True)
    parser.add_argument("--created-at", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = create_bundle(args.source_dir, args.archive_path, args.manifest_path, args.database_recovery_point, args.created_at)
    except (OSError, RecoveryError, tarfile.TarError):
        print("recovery bundle creation failed", file=sys.stderr)
        return 1
    print(f"matched upload bundle created: files={len(payload['entries'])} archive_sha256={payload['archive_sha256']} database_recovery_point={payload['database_recovery_point']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
