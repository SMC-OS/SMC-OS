"""Shared validation primitives for offline Sprint 019 recovery tools."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
import re
import unicodedata


RECOVERY_POINT_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:-]{0,198}[A-Za-z0-9])?")
UTC_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)
WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"\\|?*')
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 10_000
MAX_PATH_UTF8_BYTES = 1024
MAX_COMPONENT_UTF8_BYTES = 255
MAX_PATH_UTF16_UNITS = 1024
MAX_COMPONENT_UTF16_UNITS = 255
MAX_MEMBER_BYTES = 8**11 - 1
MAX_TOTAL_BYTES = 100 * 1024 * 1024 * 1024
PERMITTED_PAX_FIELDS = frozenset({"path"})


def validate_entry_count(count: object) -> int:
    if not isinstance(count, int) or isinstance(count, bool) or count < 0 or count > MAX_ENTRIES:
        raise ValueError("recovery entry count is invalid")
    return count


def add_member_size(total: object, member_size: object) -> int:
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < 0
        or not isinstance(member_size, int)
        or isinstance(member_size, bool)
        or member_size < 0
        or member_size > MAX_MEMBER_BYTES
        or total + member_size > MAX_TOTAL_BYTES
    ):
        raise ValueError("recovery size is invalid")
    return total + member_size


def validate_manifest_size(size: object) -> int:
    if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > MAX_MANIFEST_BYTES:
        raise ValueError("recovery manifest size is invalid")
    return size


def validate_recovery_metadata(recovery_point: object, created_at: object) -> tuple[str, str]:
    """Return canonical safe metadata or reject it before artifact creation."""
    if not isinstance(recovery_point, str) or RECOVERY_POINT_PATTERN.fullmatch(recovery_point) is None:
        raise ValueError("recovery metadata is invalid")
    if not isinstance(created_at, str) or UTC_TIMESTAMP_PATTERN.fullmatch(created_at) is None:
        raise ValueError("recovery metadata is invalid")
    try:
        parsed = datetime.fromisoformat(created_at.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError("recovery metadata is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("recovery metadata is invalid")
    return recovery_point, created_at


def validate_portable_relative_path(value: object) -> tuple[str, str]:
    """Return an exact path and its collision key, or reject unsafe names."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("recovery path is invalid")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or not posix.parts
        or posix.as_posix() != value
    ):
        raise ValueError("recovery path is invalid")

    try:
        path_utf8_bytes = len(value.encode("utf-8"))
        path_utf16_units = len(value.encode("utf-16-le")) // 2
    except UnicodeEncodeError as exc:
        raise ValueError("recovery path is invalid") from exc
    if path_utf8_bytes > MAX_PATH_UTF8_BYTES or path_utf16_units > MAX_PATH_UTF16_UNITS:
        raise ValueError("recovery path is invalid")

    collision_parts: list[str] = []
    for part in posix.parts:
        try:
            component_utf8_bytes = len(part.encode("utf-8"))
            component_utf16_units = len(part.encode("utf-16-le")) // 2
        except UnicodeEncodeError as exc:
            raise ValueError("recovery path is invalid") from exc
        if (
            part in ("", ".", "..")
            or part.endswith((" ", "."))
            or any(character in WINDOWS_FORBIDDEN_CHARACTERS or ord(character) < 32 for character in part)
            or part.split(".", 1)[0].casefold() in WINDOWS_RESERVED_NAMES
            or component_utf8_bytes > MAX_COMPONENT_UTF8_BYTES
            or component_utf16_units > MAX_COMPONENT_UTF16_UNITS
        ):
            raise ValueError("recovery path is invalid")
        collision_parts.append(unicodedata.normalize("NFC", part).casefold())
    return value, "/".join(collision_parts)
