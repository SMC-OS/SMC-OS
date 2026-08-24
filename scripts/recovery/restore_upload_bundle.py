"""Validate and restore a matched upload bundle into an empty scratch mount."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import shutil
import sys
import tarfile
import tempfile
from typing import BinaryIO

import recovery_safety as safety
from recovery_safety import validate_portable_relative_path, validate_recovery_metadata


ACTIVE_UPLOAD_MOUNT = "/var/lib/simo-os/uploads"
CHUNK_SIZE = 1024 * 1024
class RecoveryError(ValueError):
    """A validation error whose command-line presentation remains redacted."""


def _sha256_stream(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return _sha256_stream(handle)[0]


def _sha256_open_file(handle: BinaryIO) -> str:
    handle.seek(0)
    try:
        return _sha256_stream(handle)[0]
    finally:
        handle.seek(0)


def _open_regular_file(path: Path) -> tuple[BinaryIO, os.stat_result]:
    handle: BinaryIO | None = None
    try:
        before_open = path.lstat()
        if not stat.S_ISREG(before_open.st_mode) or _is_reparse(before_open):
            raise RecoveryError("recovery artifact is invalid")
        handle = path.open("rb")
        opened = os.fstat(handle.fileno())
    except OSError as exc:
        if handle is not None:
            handle.close()
        raise RecoveryError("recovery artifact is invalid") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or _is_reparse(opened)
        or not os.path.samestat(before_open, opened)
    ):
        handle.close()
        raise RecoveryError("recovery artifact is invalid")
    return handle, opened


def _require_unchanged_regular_file(
    path: Path,
    handle: BinaryIO,
    opened: os.stat_result,
    expected_digest: str,
) -> None:
    try:
        current_path = path.lstat()
        current_handle = os.fstat(handle.fileno())
    except OSError as exc:
        raise RecoveryError("recovery artifact changed during restore") from exc
    if (
        not stat.S_ISREG(current_path.st_mode)
        or not stat.S_ISREG(current_handle.st_mode)
        or _is_reparse(current_path)
        or _is_reparse(current_handle)
        or not os.path.samestat(opened, current_handle)
        or not os.path.samestat(opened, current_path)
        or _sha256_open_file(handle) != expected_digest
    ):
        raise RecoveryError("recovery artifact changed during restore")


def _is_active_mount(path: Path) -> bool:
    normalized = str(path).replace("\\", "/").rstrip("/")
    active = ACTIVE_UPLOAD_MOUNT.rstrip("/")
    if normalized == active or normalized.startswith(active + "/"):
        return True
    try:
        path.resolve(strict=False).relative_to(Path(ACTIVE_UPLOAD_MOUNT).resolve(strict=False))
    except ValueError:
        return False
    return True


def _validate_relative_path_with_key(value: object) -> tuple[str, str]:
    try:
        exact, key = validate_portable_relative_path(value)
    except ValueError as exc:
        raise RecoveryError("invalid recovery path") from exc
    return exact, key


def _validate_relative_path(value: object) -> str:
    return _validate_relative_path_with_key(value)[0]


def _validate_digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise RecoveryError("invalid digest")
    return value.lower()


def _load_manifest(handle: BinaryIO) -> tuple[str, str, dict[str, dict[str, object]]]:
    try:
        handle.seek(0)
        raw = handle.read(safety.MAX_MANIFEST_BYTES + 1)
        if len(raw) > safety.MAX_MANIFEST_BYTES:
            raise RecoveryError("manifest exceeds the permitted size")
        payload = json.loads(raw.decode("utf-8"))
        handle.seek(0)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryError("manifest is unreadable") from exc
    if not isinstance(payload, dict):
        raise RecoveryError("manifest is invalid")
    archive_digest = _validate_digest(payload.get("archive_sha256"))
    try:
        recovery_point, _created_at = validate_recovery_metadata(
            payload.get("database_recovery_point"), payload.get("created_at")
        )
    except ValueError as exc:
        raise RecoveryError("manifest recovery metadata is invalid") from exc
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise RecoveryError("manifest entries are invalid")
    try:
        safety.validate_entry_count(len(entries))
    except ValueError as exc:
        raise RecoveryError("manifest entries are invalid") from exc
    parsed: dict[str, dict[str, object]] = {}
    collision_keys: set[str] = set()
    total_size = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise RecoveryError("manifest entry is invalid")
        relative_path, collision_key = _validate_relative_path_with_key(entry.get("relative_path"))
        digest = _validate_digest(entry.get("sha256"))
        size = entry.get("size_bytes")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or relative_path in parsed
            or collision_key in collision_keys
        ):
            raise RecoveryError("manifest entry is invalid")
        try:
            total_size = safety.add_member_size(total_size, size)
        except ValueError as exc:
            raise RecoveryError("manifest aggregate size is invalid") from exc
        parsed[relative_path] = {"sha256": digest, "size_bytes": size}
        collision_keys.add(collision_key)
    return archive_digest, recovery_point, parsed


def _is_reparse(stat_result: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(stat_result, "st_file_attributes", 0) & reparse_flag)


def _validate_scratch(scratch: Path) -> tuple[Path, os.stat_result]:
    if _is_active_mount(scratch) or not scratch.is_dir() or scratch.is_symlink():
        raise RecoveryError("scratch target is invalid")
    resolved = scratch.resolve(strict=True)
    opened = resolved.lstat()
    if not stat.S_ISDIR(opened.st_mode) or _is_reparse(opened):
        raise RecoveryError("scratch target is invalid")
    if any(resolved.iterdir()):
        raise RecoveryError("scratch target is not empty")
    return resolved, opened


def _require_same_directory(
    path: Path,
    opened: os.stat_result,
    *,
    require_empty: bool,
    allowed_entry: tuple[Path, os.stat_result] | None = None,
) -> None:
    try:
        current = path.lstat()
        entries = list(path.iterdir()) if require_empty else []
    except OSError as exc:
        raise RecoveryError("scratch target changed during restore") from exc
    contents_are_valid = not entries
    if allowed_entry is not None and len(entries) == 1:
        allowed_path, allowed_opened = allowed_entry
        try:
            contents_are_valid = (
                entries[0] == allowed_path
                and os.path.samestat(allowed_opened, entries[0].lstat())
            )
        except OSError:
            contents_are_valid = False
    if (
        not stat.S_ISDIR(current.st_mode)
        or _is_reparse(current)
        or not os.path.samestat(opened, current)
        or (require_empty and not contents_are_valid)
    ):
        raise RecoveryError("scratch target changed during restore")


def _preflight_archive(archive_handle: BinaryIO, expected: dict[str, dict[str, object]]) -> None:
    archive_handle.seek(0)
    with tarfile.open(fileobj=archive_handle, mode="r:") as archive:
        seen: set[str] = set()
        collision_keys: set[str] = set()
        count = 0
        total_size = 0
        for member in archive:
            count += 1
            if count > safety.MAX_ENTRIES:
                raise RecoveryError("archive has too many members")
            name, collision_key = _validate_relative_path_with_key(member.name)
            if (
                name in seen
                or collision_key in collision_keys
                or member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE)
                or member.issparse()
                or set(member.pax_headers) - safety.PERMITTED_PAX_FIELDS
                or name not in expected
            ):
                raise RecoveryError("archive membership is invalid")
            seen.add(name)
            collision_keys.add(collision_key)
            entry = expected[name]
            if member.size > safety.MAX_MEMBER_BYTES or member.size != entry["size_bytes"]:
                raise RecoveryError("archive member size is invalid")
            total_size += member.size
            if total_size > safety.MAX_TOTAL_BYTES:
                raise RecoveryError("archive aggregate size is invalid")
            source = archive.extractfile(member)
            if source is None:
                raise RecoveryError("archive member is invalid")
            with source:
                digest, size = _sha256_stream(source)
            if size != entry["size_bytes"] or digest != entry["sha256"]:
                raise RecoveryError("archive member digest is invalid")
        if seen != set(expected):
            raise RecoveryError("archive membership is incomplete")


def _ensure_private_parent(root: Path, parts: tuple[str, ...]) -> Path:
    current = root
    for part in parts:
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise RecoveryError("private extraction path is invalid") from exc
        opened = current.lstat()
        if not stat.S_ISDIR(opened.st_mode) or _is_reparse(opened):
            raise RecoveryError("private extraction path is invalid")
    return current


def _extract_to_private_staging(
    archive_handle: BinaryIO,
    expected: dict[str, dict[str, object]],
    staging: Path,
) -> None:
    archive_handle.seek(0)
    with tarfile.open(fileobj=archive_handle, mode="r:") as archive:
        for member in archive:
            name = _validate_relative_path(member.name)
            entry = expected[name]
            parts = PurePosixPath(name).parts
            parent = _ensure_private_parent(staging, parts[:-1])
            destination = parent / parts[-1]
            source = archive.extractfile(member)
            if source is None:
                raise RecoveryError("archive member is invalid")
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            try:
                fd = os.open(destination, flags, 0o600)
            except OSError as exc:
                source.close()
                raise RecoveryError("private extraction failed") from exc
            with source, os.fdopen(fd, "w+b") as target:
                for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
                os.chmod(destination, 0o600)
                digest = _sha256_open_file(target)
                opened = os.fstat(target.fileno())
                current = destination.lstat()
                if (
                    digest != entry["sha256"]
                    or opened.st_size != entry["size_bytes"]
                    or not stat.S_ISREG(opened.st_mode)
                    or _is_reparse(current)
                    or not os.path.samestat(opened, current)
                ):
                    raise RecoveryError("restored file digest is invalid")


def _remove_private_staging(staging: Path, opened: os.stat_result) -> None:
    try:
        current = staging.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISDIR(current.st_mode) and not _is_reparse(current) and os.path.samestat(opened, current):
        shutil.rmtree(staging)


def _publish_staging(
    staging: Path,
    staging_opened: os.stat_result,
    scratch: Path,
    scratch_opened: os.stat_result,
) -> None:
    _require_same_directory(
        scratch,
        scratch_opened,
        require_empty=True,
        allowed_entry=(staging, staging_opened),
    )
    published: list[tuple[Path, Path, os.stat_result, bool]] = []
    try:
        for source in sorted(staging.iterdir(), key=lambda path: path.name):
            _require_same_directory(scratch, scratch_opened, require_empty=False)
            target = scratch / source.name
            source_opened = source.lstat()
            if stat.S_ISREG(source_opened.st_mode):
                os.link(source, target)
                source.unlink()
                is_directory = False
            elif stat.S_ISDIR(source_opened.st_mode) and not _is_reparse(source_opened):
                os.rename(source, target)
                is_directory = True
            else:
                raise RecoveryError("private extraction output is invalid")
            target_opened = target.lstat()
            if not os.path.samestat(source_opened, target_opened):
                raise RecoveryError("scratch publication failed")
            published.append((source, target, target_opened, is_directory))
        current = scratch.lstat()
        if not os.path.samestat(scratch_opened, current) or _is_reparse(current):
            raise RecoveryError("scratch target changed during restore")
    except BaseException:
        for source, target, opened, is_directory in reversed(published):
            try:
                current = target.lstat()
                if os.path.samestat(opened, current):
                    if is_directory:
                        os.rename(target, source)
                    else:
                        os.link(target, source)
                        target.unlink()
            except OSError:
                pass
        raise


def restore_bundle(archive_path: Path, manifest_path: Path, scratch_upload_dir: Path) -> tuple[int, str, str]:
    scratch, scratch_opened = _validate_scratch(scratch_upload_dir)
    _require_same_directory(scratch, scratch_opened, require_empty=True)
    staging = Path(tempfile.mkdtemp(prefix=".simo-restore-incomplete-", dir=scratch))
    os.chmod(staging, 0o700)
    staging_opened = staging.lstat()
    if (
        not stat.S_ISDIR(staging_opened.st_mode)
        or _is_reparse(staging_opened)
        or staging_opened.st_dev != scratch_opened.st_dev
    ):
        raise RecoveryError("private extraction staging is invalid")
    _require_same_directory(
        scratch,
        scratch_opened,
        require_empty=True,
        allowed_entry=(staging, staging_opened),
    )
    remove_staging = True
    try:
        manifest_handle, manifest_opened = _open_regular_file(manifest_path)
        with manifest_handle:
            manifest_digest = _sha256_open_file(manifest_handle)
            archive_digest, recovery_point, expected = _load_manifest(manifest_handle)
            _require_unchanged_regular_file(manifest_path, manifest_handle, manifest_opened, manifest_digest)
            archive_handle, archive_opened = _open_regular_file(archive_path)
            with archive_handle:
                if _sha256_open_file(archive_handle) != archive_digest:
                    raise RecoveryError("archive digest mismatch")
                _preflight_archive(archive_handle, expected)
                _require_unchanged_regular_file(archive_path, archive_handle, archive_opened, archive_digest)
                _require_same_directory(staging, staging_opened, require_empty=False)
                _extract_to_private_staging(archive_handle, expected, staging)
                _require_same_directory(staging, staging_opened, require_empty=False)
                _require_unchanged_regular_file(archive_path, archive_handle, archive_opened, archive_digest)
            _require_unchanged_regular_file(manifest_path, manifest_handle, manifest_opened, manifest_digest)
        _publish_staging(staging, staging_opened, scratch, scratch_opened)
        return len(expected), archive_digest, recovery_point
    except BaseException:
        try:
            current_scratch = scratch.lstat()
            if not os.path.samestat(scratch_opened, current_scratch) or any(
                child != staging for child in scratch.iterdir()
            ):
                remove_staging = False
        except OSError:
            remove_staging = False
        raise
    finally:
        if remove_staging:
            _remove_private_staging(staging, staging_opened)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore an offline matched upload bundle into an empty scratch directory.")
    parser.add_argument("--archive-path", required=True, type=Path)
    parser.add_argument("--manifest-path", required=True, type=Path)
    parser.add_argument("--scratch-upload-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        count, digest, recovery_point = restore_bundle(args.archive_path, args.manifest_path, args.scratch_upload_dir)
    except (OSError, RecoveryError, tarfile.TarError):
        print("recovery bundle restore failed", file=sys.stderr)
        return 1
    print(f"matched upload bundle restored: files={count} archive_sha256={digest} database_recovery_point={recovery_point}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
